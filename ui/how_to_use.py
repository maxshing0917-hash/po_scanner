# how_to_use.py — HowToUseDialog (extracted from po_scanner.py)
#
# Dependencies (from po_scanner.py):
#   _DraggableDialog, P, _s, _shadow, _mk_btn
#
# To re-integrate: import HowToUseDialog from here and wire up the two call sites:
#   CarrierSelectPage: help_btn.clicked.connect(lambda: HowToUseDialog(self).exec_())
#   ScanTablePage._show_help: HowToUseDialog(self).exec_()

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class HowToUseDialog(_DraggableDialog):
    _SLIDES = [
        ('🔍', 'Scan Tracking',
         'Use a barcode scanner or tap a cell in the Tracking column to enter a tracking '
         'number manually.'),
        ('📷', 'Scan PO',
         'Tap a cell in the PO column to open the camera.\n\n'
         'Point the camera at the PO number on the package.'),
        ('✅', 'Confirm PO',
         'After scanning, review the detected PO number on the confirmation screen.\n\n'
         'You can edit any part of the PO before tapping Confirm to save it.'),
        ('💾', 'Save & Switch Carrier',
         'Tap Save to write all current records to a CSV file.\n\n'
         'Tap the carrier badge in the top-left corner to go back and select a '
         'different carrier.'),
        ('📊', 'Export to Excel',
         'One-time setup: Open Excel → press Alt+F11 → import PO_Import.bas → assign '
         'the ImportTodayFromCSV macro to a button.\n\n'
         'Daily use: click the button to pull today\'s records into Excel. '
         'Rows that already exist are skipped automatically.'),
        ('💡', 'Tips',
         '• Use Batch Scan mode to fill multiple PO numbers at once.'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = 0
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(_s(760))

        p = _s(18)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(8))

        card = QWidget()
        card.setStyleSheet(f'background: {P["bg_start"]}; border-radius: {_s(20)}px;')
        _shadow(card, blur=40, dy=10)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # ── header ──
        header = QWidget()
        header.setFixedHeight(_s(62))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(20), 0, _s(16), 0)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFont(QFont('Segoe UI', _s(22)))
        self._icon_lbl.setStyleSheet('color: white; background: transparent;')

        self._title_lbl = QLabel()
        self._title_lbl.setFont(QFont('Segoe UI', _s(20), QFont.Bold))
        self._title_lbl.setStyleSheet('color: white; background: transparent;')

        close_btn = QPushButton('✕')
        close_btn.setFixedSize(_s(38), _s(38))
        close_btn.setFont(QFont('Segoe UI', _s(16)))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: rgba(255,255,255,180);
                border: none;
                border-radius: {_s(19)}px;
            }}
            QPushButton:hover   {{ background: rgba(255,255,255,30); color: white; }}
            QPushButton:pressed {{ background: rgba(255,255,255,50); }}
        """)
        close_btn.clicked.connect(self.reject)

        h_lo.addWidget(self._icon_lbl)
        h_lo.addSpacing(_s(8))
        h_lo.addWidget(self._title_lbl)
        h_lo.addStretch()
        h_lo.addWidget(close_btn)
        lo.addWidget(header)

        # ── content ──
        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(40), _s(30), _s(40), _s(24))
        c_lo.setSpacing(_s(24))

        self._body_lbl = QLabel()
        self._body_lbl.setFont(QFont('Segoe UI', _s(19)))
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setStyleSheet(f'color: {P["text"]}; background: transparent;')
        self._body_lbl.setMinimumHeight(_s(190))
        self._body_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        c_lo.addWidget(self._body_lbl)

        # dot indicators
        dot_row = QHBoxLayout()
        dot_row.setSpacing(_s(10))
        dot_row.addStretch()
        self._dots = []
        for _ in range(len(self._SLIDES)):
            dot = QLabel('●')
            dot.setFont(QFont('Segoe UI', _s(11)))
            dot.setStyleSheet('background: transparent;')
            dot_row.addWidget(dot)
            self._dots.append(dot)
        dot_row.addStretch()
        c_lo.addLayout(dot_row)

        # prev / next buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(16))
        self._prev_btn = _mk_btn('← Prev', P['btn_sec'], h=72, fs=19, min_w=160)
        self._next_btn = _mk_btn('Next →', P['btn_pri'], h=72, fs=19, min_w=160)
        self._prev_btn.setAutoDefault(False)
        self._next_btn.setAutoDefault(False)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        btn_row.addWidget(self._prev_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._next_btn)
        c_lo.addLayout(btn_row)

        lo.addWidget(content)
        self._refresh()

    def _refresh(self):
        icon, title, body = self._SLIDES[self._page]
        self._icon_lbl.setText(icon)
        self._title_lbl.setText(title)
        self._body_lbl.setText(body)
        active   = f'color: {P["btn_pri"]}; background: transparent;'
        inactive = f'color: {P["subtitle"]}; background: transparent;'
        for i, dot in enumerate(self._dots):
            dot.setStyleSheet(active if i == self._page else inactive)
        self._prev_btn.setVisible(self._page > 0)
        self._next_btn.setText('Got it' if self._page == len(self._SLIDES) - 1 else 'Next →')

    def _go_prev(self):
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _go_next(self):
        if self._page < len(self._SLIDES) - 1:
            self._page += 1
            self._refresh()
        else:
            self.accept()
