# ui_utils.py — Shared UI utilities for PO Scanner
#
# Imported by: po_scanner.py, scan_table_ui.py (and any future UI modules)

from PyQt5.QtWidgets import QPushButton, QGraphicsDropShadowEffect, QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

# ── DPI-relative scale ────────────────────────────────────────────────────────
# _S is set in main() after QApplication is created, based on screen resolution.
# All other modules should call _s() — never read _S directly.

_S: float = 1.0

def _s(px) -> int:
    """Scale a pixel value proportionally to the logical screen height."""
    return max(1, int(round(px * _S)))


# ── Palette ───────────────────────────────────────────────────────────────────

P = {
    'bg_start':   '#F5E6D3',
    'bg_end':     '#E8DCC8',
    'panel':      '#FFFFFF',
    'title':      '#6B4423',
    'text':       '#3D3228',
    'subtitle':   '#8B7355',
    'cam_bg':     '#2D2416',
    'btn_pri':    '#D4A574',
    'btn_suc':    '#6BA547',
    'btn_sec':    '#8B7355',
    'border':     '#E8DCC8',
    'res_bg':     '#EDF7ED',
    'res_border': '#6BA547',
}


# ── Table column indices ──────────────────────────────────────────────────────

COL_TRK = 0   # Tracking Number
COL_PO  = 1   # PO prefix
COL_NUM = 2   # PO Number
COL_RN  = 3   # RN
COL_PC  = 4   # PC
N_COLS  = 5

# ── UserRole convention ───────────────────────────────────────────────────────
# Every QTableWidgetItem uses Qt.UserRole as a boolean "is placeholder" flag.
#   item.setData(Qt.UserRole, True)  → cell shows greyed-out placeholder text, treat as empty
#   item.setData(Qt.UserRole, False) → cell contains real user data
# Always check `not item.data(Qt.UserRole)` before reading a cell value.


# ── Helper functions ──────────────────────────────────────────────────────────

def _shadow(widget, blur=15, dy=4):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, 30))
    widget.setGraphicsEffect(eff)


def _darken(hex_color: str, amt: int = 18) -> str:
    c = QColor(hex_color)
    return QColor(
        max(0, c.red()   - amt),
        max(0, c.green() - amt),
        max(0, c.blue()  - amt),
    ).name()


def _force_upper(edit: QLineEdit):
    """Force a QLineEdit to always display uppercase, preserving cursor position."""
    def _on_changed(text):
        upper = text.upper()
        if text != upper:
            pos = edit.cursorPosition()
            edit.blockSignals(True)
            edit.setText(upper)
            edit.setCursorPosition(pos)
            edit.blockSignals(False)
    edit.textChanged.connect(_on_changed)


def _mk_btn(label: str, color: str, h: int = 44, fs: int = 12,
            min_w: int = 100) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(_s(h))
    b.setMinimumWidth(_s(min_w))
    b.setCursor(Qt.PointingHandCursor)
    b.setFont(QFont('Segoe UI', _s(fs), QFont.Bold))
    b.setStyleSheet(f"""
        QPushButton {{
            background: {color};
            color: white;
            border: none;
            border-radius: {_s(8)}px;
            padding: 0 {_s(14)}px;
        }}
        QPushButton:hover   {{ background: {_darken(color)}; }}
        QPushButton:pressed {{ background: {_darken(color, 30)}; }}
        QPushButton:disabled {{
            background: #C8BAB0;
            color: #E8DDD4;
        }}
    """)
    return b
