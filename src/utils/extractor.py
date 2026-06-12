"""
Extractor - PO and Tracking Number extraction
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ExtractionResult:
    po: Optional[str] = None
    po_candidates: list = field(default_factory=list)
    tracking: Optional[str] = None
    tracking_candidates: list = field(default_factory=list)
    po_source: str = ""
    tracking_source: str = ""
    ocr_carrier: Optional[str] = None


# -- PO ---------------------------------------------------------------

# Full PO: prefix(2) + Number(5 alphanumeric) + RN(3 digits) + PC(6 alphanumeric) = 16 chars
_PO_FULL = re.compile(r'^[AWSIBXN][A-Z0-9]{6}\d{3}[A-Z0-9]{6}$', re.IGNORECASE)

# Short 7-char (PO 2 + Number 5)
_PO_7CHAR = re.compile(r'^[AWSIBXN][A-Z0-9]{6}$', re.IGNORECASE)

# SG vendor PO: SG + 7 digits (no RN, no PC)
_PO_SG = re.compile(r'^SG\d{7}$', re.IGNORECASE)

_PO_VALID_STARTS = set('AWSIBXN')


def _fix_po_second_char(token: str) -> str:
    """
    The second character of a PO prefix is never O or I.
    OCR often misreads 0 as O and 1 as I.
    For SG vendor POs, OCR may misread G as 6.
    Only corrects when the first character is a valid PO start letter.
    """
    if len(token) >= 2 and token[0] in _PO_VALID_STARTS:
        if token[1] == 'O':
            return token[0] + '0' + token[2:]
        if token[1] == 'I':
            return token[0] + '1' + token[2:]
        if token[0] == 'S' and token[1] == '6':
            return token[0] + 'G' + token[2:]
    return token


def _normalize_token(token: str) -> str:
    """
    Apply all OCR corrections to a potential PO token.
    Step 1 — first char: '1'/'L' → 'I' for standard PO lengths (7/15-16 chars);
             '5' → 'S' for SG vendor PO length (9 chars).
    Step 2 — second char: delegate to _fix_po_second_char (O→0, I→1, S+6→SG).
             Must run after step 1 so the first-char check in that function is correct.
    """
    if len(token) in (7, 15, 16) and token[0] in ('1', 'L'):
        token = 'I' + token[1:]
    elif len(token) == 9 and token[0] == '5':
        token = 'S' + token[1:]
    return _fix_po_second_char(token)


def _try_match_po(token: str) -> 'str | None':
    """Try to extract a valid PO from a single token. Returns the PO string or None."""
    token = _normalize_token(token.upper())
    if _PO_FULL.match(token) or _PO_7CHAR.match(token) or _PO_SG.match(token):
        return token

    # 15-char rescue: valid 7-char prefix, one char missing from RN or PC
    if len(token) == 15 and _PO_7CHAR.match(token[:7]):
        # Case 4: RN truncated to 2 digits (token[9] is a letter instead of digit)
        if token[7:9].isdigit() and not token[9].isdigit():
            candidate = token[:9] + '0' + token[9:]
            if _PO_FULL.match(candidate):
                return candidate
        # Case 3: PC missing leading 'D' (token[10] is a digit instead of letter)
        if token[7:10].isdigit() and len(token) > 10 and token[10].isdigit():
            candidate = token[:10] + 'D' + token[10:]
            if _PO_FULL.match(candidate):
                return candidate

    return None


def _po_candidates_from_line(line: str) -> list[str]:
    """
    Find all valid PO candidates (7-char or 15/16-char) from a single line.
    Case 1: split by any non-alphanumeric character and check each token.
    Case 2: fallback — find 'PO' keyword and extract what follows.
    """
    # Case 1: split by any non-alphanumeric separator (spaces and symbols)
    result = []
    for token in re.split(r'[^A-Za-z0-9]', line):
        if not token:
            continue
        candidate = _try_match_po(token)
        if candidate and candidate not in result:
            result.append(candidate)
    if result:  
        return result

    # Case 2: find 'PO' keyword followed by a valid PO start char, extract 7 or 15/16-char
    upper_line = line.upper()
    for m in re.finditer(r'PO([AWSIBXN])', upper_line):
        start = m.start(1)
        for length in (16, 7):
            candidate = _try_match_po(upper_line[start:start + length])
            if candidate and candidate not in result:
                result.append(candidate)
                break
    return result


def extract_po(ocr_lines: list[str], blacklist: list[str] | None = None) -> tuple[list[str], str]:
    """
    Extract all PO candidates from OCR text lines.
    16-char takes priority: if any 16-char candidates exist, only those are returned.

    Returns:
        (candidates, source)  candidates are in order of appearance
    """
    # Normalize each blacklist entry the same way tokens are normalized,
    # so entries like 'SONAME1' still match after _fix_po_second_char converts it to 'S0NAME1'.
    blocked = {_normalize_token(w.upper()) for w in (blacklist or [])}
    seen: set[str] = set()
    candidates_full: list[str] = []
    candidates_7: list[str] = []

    for line in ocr_lines:
        for token in _po_candidates_from_line(line):
            if token in seen or token in blocked:
                continue
            seen.add(token)
            if len(token) >= 15:
                candidates_full.append(token)
            else:
                candidates_7.append(token)

    if candidates_full and candidates_7:
        candidates = candidates_full + candidates_7  # full-length first, 7-char appended
    else:
        candidates = candidates_full if candidates_full else candidates_7
    return candidates, ('token' if candidates else '')


# -- Tracking ---------------------------------------------------------

# Amazon: TBA + 9 or more digits
_TRACKING_AMAZON = re.compile(r'\bTBA\d{9,}\b', re.IGNORECASE)

# UPS: 1Z prefix, 16 alphanumeric chars after (18 total)
_TRACKING_UPS_START = re.compile(r'1Z([A-Z0-9 ]{16,30})', re.IGNORECASE)

# FedEx barcode: 96 prefix + 32 digits = 34 digits total
_TRACKING_FEDEX_BARCODE = re.compile(r'^96\d{32}$')

# FedEx OCR: spaced digit string, e.g. "9622 0422 1 (000 000 0000) 0 00 3805 9009 9850"
_TRACKING_FEDEX_SPACED = re.compile(r'^[\d\s()]{20,80}$')

# USPS: 420 + 5-digit ZIP + tracking digits, total 28-35 digits
_TRACKING_USPS = re.compile(r'^420\d{25,32}$')


_ALL_CARRIERS = ['amazon', 'ups', 'usps', 'fedex']

# Word-boundary regex — Amazon excluded (detected via TBA prefix instead)
_CARRIER_KEYWORD_RE = re.compile(r'\b(usps|fedex|ups)\b', re.IGNORECASE)


def detect_carrier_from_keywords(ocr_lines: list[str]) -> Optional[str]:
    """Scan OCR lines for carrier name keywords. Returns carrier string or None."""
    for line in ocr_lines:
        m = _CARRIER_KEYWORD_RE.search(line)
        if m:
            return m.group(1).lower()
    return None



def _clean_ups(raw: str) -> Optional[str]:
    """Clean a spaced UPS tracking number into the standard 18-char format."""
    cleaned = '1Z' + re.sub(r'\s+', '', raw).upper()
    if re.fullmatch(r'1Z[A-Z0-9]{16}', cleaned):
        return cleaned
    return None


def _try_carrier(text: str, carrier: str) -> tuple[Optional[str], str]:
    """Try matching a single carrier pattern. Returns (value, source) or (None, '')."""
    if carrier == 'amazon':
        if _TRACKING_AMAZON.match(text):
            return text.upper(), 'amazon'

    elif carrier == 'ups':
        m = _TRACKING_UPS_START.match(text)
        if m:
            result = _clean_ups(m.group(1))
            if result:
                return result, 'ups'

    elif carrier == 'usps':
        digits = re.sub(r'[\s()]', '', text)
        if _TRACKING_USPS.match(digits):
            return digits, 'usps'

    elif carrier == 'fedex':
        digits = re.sub(r'[\s()]', '', text)
        if _TRACKING_FEDEX_BARCODE.match(digits):
            return digits, 'fedex'
        if _TRACKING_FEDEX_SPACED.match(text) and digits.isdigit() and 15 <= len(digits) <= 40:
            return digits, 'fedex'

    return None, ''


def _classify_tracking(text: str, forced_carrier: Optional[str] = None) -> tuple[Optional[str], str]:
    """Auto-detect carrier and extract tracking number from text."""
    text = text.strip()
    carriers = [forced_carrier] if forced_carrier else _ALL_CARRIERS
    for c in carriers:
        result, source = _try_carrier(text, c)
        if result:
            return result, source
    return None, ''



def extract_tracking(ocr_lines: list[str], forced_carrier: Optional[str] = None) -> tuple[Optional[str], str]:
    """OCR fallback: auto-detect carrier and extract tracking number from text lines."""
    for line in ocr_lines:
        tracking, source = _classify_tracking(line, forced_carrier)
        if tracking:
            return tracking, source
    return None, ''
