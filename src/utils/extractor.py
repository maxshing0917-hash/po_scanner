"""
Extractor - PO extraction

PO numbers are scanned from physical package labels via OCR, which frequently
misreads certain characters (O↔0, I↔1/L, S↔5, G↔6). The correction rules
in this module exist to recover valid POs from these misreadings.

Some rules are carrier-specific (e.g. SG vendor POs, PC prefix conventions)
and were added based on observed OCR errors from real scan data.
"""

import re
from typing import Optional


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
        # 'D' is hardcoded because PC on this carrier always starts with D.
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
