# dialogs.py — All modal dialog classes for PO Scanner
#
# Imported by: po_scanner.py
# Dependencies: ui/ui_utils.py (P, _s, _shadow, _mk_btn, _force_upper)

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QRect, QPoint
from PyQt5.QtGui import QFont, QColor, QPainter, QPainterPath, QPen

from ui.ui_utils import P, _s, _shadow, _mk_btn, _force_upper


# ── Draggable frameless dialog base ──────────────────────────────────────────

class _DraggableDialog(QDialog):
    """Frameless QDialog that can be dragged by clicking anywhere."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() == Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)


# ── Alert dialog ──────────────────────────────────────────────────────────────

class AlertDialog(_DraggableDialog):
    def __init__(self, message: str, parent=None, title: str = 'Notice'):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(_s(700))

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

        header = QWidget()
        header.setFixedHeight(_s(62))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(26), 0, _s(26), 0)
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont('Segoe UI', _s(20), QFont.Bold))
        title_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addWidget(title_lbl)
        lo.addWidget(header)

        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(36), _s(28), _s(36), _s(28))
        c_lo.setSpacing(_s(24))

        msg = QLabel(message)
        msg.setFont(QFont('Segoe UI', _s(19)))
        msg.setWordWrap(True)
        msg.setStyleSheet(f'color: {P["text"]}; background: transparent;')
        c_lo.addWidget(msg)

        btn = _mk_btn('OK', P['btn_pri'], h=72, fs=20, min_w=200)
        btn.clicked.connect(self.accept)
        c_lo.addWidget(btn)
        lo.addWidget(content)


# ── Save-warn dialog ──────────────────────────────────────────────────────────

class _SaveWarnDialog(_DraggableDialog):
    """Warning dialog — lists an issue, offers a back and a confirm button."""
    def __init__(self, message: str, parent=None,
                 confirm_text: str = 'Save anyway', confirm_color: str = None):
        super().__init__(parent)
        self.setMinimumWidth(_s(780))
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

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

        header = QWidget()
        header.setFixedHeight(_s(62))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(26), 0, _s(26), 0)
        icon_lbl = QLabel('⚠')
        icon_lbl.setFont(QFont('Segoe UI', _s(20)))
        icon_lbl.setStyleSheet('color: #FFD580; background: transparent;')
        warn_lbl = QLabel('Warning')
        warn_lbl.setFont(QFont('Segoe UI', _s(20), QFont.Bold))
        warn_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addStretch()
        h_lo.addWidget(icon_lbl)
        h_lo.addSpacing(_s(10))
        h_lo.addWidget(warn_lbl)
        h_lo.addStretch()
        lo.addWidget(header)

        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(44), _s(36), _s(44), _s(36))
        c_lo.setSpacing(_s(30))

        msg_lbl = QLabel(message)
        msg_lbl.setFont(QFont('Segoe UI', _s(19)))
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignCenter)
        msg_lbl.setTextFormat(Qt.RichText)
        msg_lbl.setStyleSheet(f'color: {P["text"]}; background: transparent;')
        c_lo.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(20))
        back_btn = _mk_btn('Go back',    P['btn_sec'], h=80, fs=20, min_w=220)
        conf_btn = _mk_btn(confirm_text, confirm_color or P['btn_suc'], h=80, fs=20, min_w=220)
        back_btn.setAutoDefault(False)
        conf_btn.setAutoDefault(False)
        back_btn.clicked.connect(self.reject)
        conf_btn.clicked.connect(self.accept)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        btn_row.addWidget(conf_btn)
        c_lo.addLayout(btn_row)
        lo.addWidget(content)


# ── Tracking edit dialog ──────────────────────────────────────────────────────

class TrackingEditDialog(_DraggableDialog):
    """Manual entry for tracking or PO — frameless card with context info strip."""

    def __init__(self, current_value: str = '', parent=None,
                 title: str = 'Enter Tracking',
                 package_num: int = 0,
                 context_label: str = '',
                 min_len: int = 4):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(_s(780))
        self.value = ''
        self._min_len = min_len
        self._build_ui(current_value, title, package_num, context_label)

    def _build_ui(self, current_value, title, package_num, context_label):
        p = _s(20)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(8))

        card = QWidget()
        card.setStyleSheet(f'background: {P["bg_start"]}; border-radius: {_s(20)}px;')
        _shadow(card, blur=40, dy=10)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # ── header strip ─────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(_s(70))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(28), 0, _s(28), 0)
        h_lo.setSpacing(_s(16))

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
        title_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addWidget(title_lbl)
        h_lo.addStretch()

        info_parts = []
        if package_num:
            info_parts.append(f'Package  #{package_num}')
        if context_label:
            info_parts.append(context_label)
        if info_parts:
            info_lbl = QLabel('   |   '.join(info_parts))
            info_lbl.setFont(QFont('Segoe UI', _s(18)))
            info_lbl.setStyleSheet('color: rgba(255,255,255,200); background: transparent;')
            h_lo.addWidget(info_lbl)

        lo.addWidget(header)

        # ── content ───────────────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(36), _s(30), _s(36), _s(30))
        c_lo.setSpacing(_s(24))

        self._edit = QLineEdit()
        self._edit.setText(current_value.upper())
        self._edit.setFixedHeight(_s(110))
        self._edit.setFont(QFont('Segoe UI', _s(50)))
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: {_s(3)}px solid {P['border']};
                border-radius: {_s(10)}px;
                padding: {_s(14)}px {_s(18)}px;
                color: {P['text']};
            }}
            QLineEdit:focus {{ border-color: {P['btn_pri']}; }}
        """)
        _force_upper(self._edit)
        self._edit.returnPressed.connect(self._confirm)
        c_lo.addWidget(self._edit)

        self._warn_lbl = QLabel(f'Minimum {self._min_len} character{"s" if self._min_len != 1 else ""} required')
        self._warn_lbl.setFont(QFont('Segoe UI', _s(18)))
        self._warn_lbl.setStyleSheet('color: #EF4444; background: transparent;')
        self._warn_lbl.setVisible(False)
        c_lo.addWidget(self._warn_lbl)

        btn_row = QHBoxLayout()
        cancel_btn        = _mk_btn('Cancel',  P['btn_sec'], h=72, fs=20, min_w=180)
        self._confirm_btn = _mk_btn('Confirm', P['btn_pri'], h=72, fs=20, min_w=180)
        cancel_btn.setAutoDefault(False)
        self._confirm_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self._confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._confirm_btn)
        c_lo.addLayout(btn_row)

        lo.addWidget(content)

        self._edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed(current_value)
        QTimer.singleShot(0, self._edit.setFocus)

    def _on_text_changed(self, text: str):
        valid = len(text.strip()) >= self._min_len
        self._confirm_btn.setEnabled(valid)
        self._warn_lbl.setVisible(bool(text.strip()) and not valid)

    def _confirm(self):
        self.value = self._edit.text().strip()
        if self.value and len(self.value) >= self._min_len:
            self.accept()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            w  = max(_s(780), int(pg.width() * 0.70))
            self.setFixedWidth(w)
            self.adjustSize()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + int(pg.height() * 0.08)
            self.move(x, y)
        return super().exec_()


# ── PO edit dialog (light theme, 4 fields) ───────────────────────────────────

class _POEditDialog(_DraggableDialog):

    def __init__(self, po_parts: dict, parent=None,
                 package_num: int = 0, tracking_tail: str = ''):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.po_value     = po_parts.get('po', '')
        self.number_value = po_parts.get('number', '')
        self.rn_value     = po_parts.get('rn', '')
        self.pc_value     = po_parts.get('pc', '')
        self._build_ui(package_num, tracking_tail)

    def _build_ui(self, package_num: int, tracking_tail: str):
        p = _s(20)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(8))

        card = QWidget()
        card.setStyleSheet(f'background: {P["bg_start"]}; border-radius: {_s(20)}px;')
        _shadow(card, blur=40, dy=10)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(_s(70))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(28), 0, _s(28), 0)
        h_lo.setSpacing(_s(16))
        title_lbl = QLabel('Edit PO')
        title_lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
        title_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addWidget(title_lbl)
        h_lo.addStretch()
        info_parts = []
        if package_num:
            info_parts.append(f'Package  #{package_num}')
        if tracking_tail:
            info_parts.append(f'Tracking  ···{tracking_tail}')
        if info_parts:
            info_lbl = QLabel('   |   '.join(info_parts))
            info_lbl.setFont(QFont('Segoe UI', _s(18)))
            info_lbl.setStyleSheet('color: rgba(255,255,255,200); background: transparent;')
            h_lo.addWidget(info_lbl)
        lo.addWidget(header)

        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(36), _s(30), _s(36), _s(30))
        c_lo.setSpacing(_s(24))

        FIELD_H = _s(100)
        EDIT_SS = f"""
            QLineEdit {{
                background: white;
                border: {_s(3)}px solid {P['border']};
                border-radius: {_s(10)}px;
                padding: {_s(10)}px {_s(18)}px;
                color: {P['text']};
            }}
            QLineEdit:focus {{ border-color: {P['btn_pri']}; }}
        """

        fields_row = QHBoxLayout()
        fields_row.setSpacing(_s(20))

        def _add_field(label_text, widget, stretch=1):
            col_w = QWidget()
            col_w.setStyleSheet('background: transparent;')
            cl = QVBoxLayout(col_w)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(_s(8))
            lbl = QLabel(label_text)
            lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
            lbl.setStyleSheet(f'color: {P["title"]}; background: transparent;')
            cl.addWidget(lbl)
            cl.addWidget(widget)
            fields_row.addWidget(col_w, stretch)

        from PyQt5.QtCore import QRegExp
        from PyQt5.QtGui import QRegExpValidator

        self._po_edit = QLineEdit(self.po_value)
        self._po_edit.setFixedHeight(FIELD_H)
        self._po_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._po_edit)
        self._po_edit.setStyleSheet(EDIT_SS)
        self._po_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._po_edit))
        _add_field('PO', self._po_edit, stretch=1)

        self._num_edit = QLineEdit(self.number_value)
        self._num_edit.setFixedHeight(FIELD_H)
        self._num_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._num_edit)
        self._num_edit.setStyleSheet(EDIT_SS)
        self._num_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._num_edit))
        _add_field('Number', self._num_edit, stretch=2)

        self._rn_edit = QLineEdit(self.rn_value)
        self._rn_edit.setFixedHeight(FIELD_H)
        self._rn_edit.setFont(QFont('Segoe UI', _s(44)))
        self._rn_edit.setValidator(QRegExpValidator(QRegExp(r'\d{0,3}'), self._rn_edit))
        self._rn_edit.setStyleSheet(EDIT_SS)
        self._rn_edit.setInputMethodHints(Qt.ImhDigitsOnly)
        _add_field('RN', self._rn_edit, stretch=1)

        self._pc_btn = QPushButton()
        self._pc_btn.setFixedHeight(FIELD_H)
        self._pc_btn.setFont(QFont('Segoe UI', _s(44)))
        self._pc_btn.setAutoDefault(False)
        self._refresh_pc_btn()
        self._pc_btn.clicked.connect(self._on_pick_pc)
        _add_field('PC', self._pc_btn, stretch=1)

        c_lo.addLayout(fields_row)

        btn_row = QHBoxLayout()
        cancel_btn        = _mk_btn('Cancel',  P['btn_sec'], h=72, fs=20, min_w=180)
        self._confirm_btn = _mk_btn('Confirm', P['btn_pri'], h=72, fs=20, min_w=180)
        cancel_btn.setAutoDefault(False)
        self._confirm_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self._confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._confirm_btn)
        c_lo.addLayout(btn_row)

        lo.addWidget(content)
        QTimer.singleShot(0, self._po_edit.setFocus)

    def _refresh_pc_btn(self):
        filled = bool(self.pc_value)
        color = P['btn_pri'] if filled else P['subtitle']
        self._pc_btn.setText(self.pc_value if filled else '— pick —')
        self._pc_btn.setStyleSheet(
            f'QPushButton {{ background: white; color: {color};'
            f' border: {_s(3)}px solid {P["border"]}; border-radius: {_s(10)}px;'
            f' padding: {_s(10)}px {_s(18)}px; text-align: left; }}'
            f'QPushButton:hover {{ border-color: {P["btn_pri"]}; }}'
        )

    def _on_pick_pc(self):
        dlg = _PCPickerDialog(self.pc_value, self, light_theme=True)
        if dlg.exec_() == _PCPickerDialog.Accepted:
            self.pc_value = dlg.pc_value
            self._refresh_pc_btn()

    def _on_confirm(self):
        self.po_value     = self._po_edit.text().strip()
        self.number_value = self._num_edit.text().strip()
        self.rn_value     = self._rn_edit.text().strip()
        self.accept()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            w  = max(_s(780), int(pg.width() * 0.70))
            self.setFixedWidth(w)
            self.adjustSize()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + int(pg.height() * 0.08)
            self.move(x, y)
        return super().exec_()


# ── Combined edit dialog (Tracking + PO fields) ───────────────────────────────

class _EditAllDialog(_DraggableDialog):

    def __init__(self, tracking: str, po_parts: dict, parent=None, package_num: int = 0):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.tracking_value = tracking
        self.po_value       = po_parts.get('po', '')
        self.number_value   = po_parts.get('number', '')
        self.rn_value       = po_parts.get('rn', '')
        self.pc_value       = po_parts.get('pc', '')
        self._build_ui(package_num)

    def _build_ui(self, package_num):
        from PyQt5.QtCore import QRegExp
        from PyQt5.QtGui import QRegExpValidator
        p = _s(20)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(8))

        card = QWidget()
        card.setStyleSheet(f'background: {P["bg_start"]}; border-radius: {_s(20)}px;')
        _shadow(card, blur=40, dy=10)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(_s(70))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(28), 0, _s(28), 0)
        h_lo.setSpacing(_s(16))
        title_lbl = QLabel(f'Edit — Package #{package_num}' if package_num else 'Edit')
        title_lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
        title_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addWidget(title_lbl)
        h_lo.addStretch()
        lo.addWidget(header)

        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(36), _s(30), _s(36), _s(30))
        c_lo.setSpacing(_s(20))

        FIELD_H = _s(100)
        EDIT_SS = f"""
            QLineEdit {{
                background: white;
                border: {_s(3)}px solid {P['border']};
                border-radius: {_s(10)}px;
                padding: {_s(10)}px {_s(18)}px;
                color: {P['text']};
            }}
            QLineEdit:focus {{ border-color: {P['btn_pri']}; }}
        """

        def _make_label(text):
            lbl = QLabel(text)
            lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
            lbl.setStyleSheet(f'color: {P["title"]}; background: transparent;')
            return lbl

        def _add_field(label_text, widget, stretch=1):
            col_w = QWidget()
            col_w.setStyleSheet('background: transparent;')
            cl = QVBoxLayout(col_w)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(_s(8))
            cl.addWidget(_make_label(label_text))
            cl.addWidget(widget)
            fields_row.addWidget(col_w, stretch)

        # ── Tracking (full width) ─────────────────────────────────────────────
        trk_wrap = QWidget()
        trk_wrap.setStyleSheet('background: transparent;')
        trk_vlo = QVBoxLayout(trk_wrap)
        trk_vlo.setContentsMargins(0, 0, 0, 0)
        trk_vlo.setSpacing(_s(8))
        trk_vlo.addWidget(_make_label('Tracking'))
        self._trk_edit = QLineEdit(self.tracking_value)
        self._trk_edit.setFixedHeight(FIELD_H)
        self._trk_edit.setFont(QFont('Segoe UI', _s(44)))
        self._trk_edit.setStyleSheet(EDIT_SS)
        _force_upper(self._trk_edit)
        trk_vlo.addWidget(self._trk_edit)
        c_lo.addWidget(trk_wrap)

        # ── PO row ────────────────────────────────────────────────────────────
        fields_row = QHBoxLayout()
        fields_row.setSpacing(_s(20))

        self._po_edit = QLineEdit(self.po_value)
        self._po_edit.setFixedHeight(FIELD_H)
        self._po_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._po_edit)
        self._po_edit.setStyleSheet(EDIT_SS)
        self._po_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._po_edit))
        _add_field('PO', self._po_edit, stretch=2)

        self._num_edit = QLineEdit(self.number_value)
        self._num_edit.setFixedHeight(FIELD_H)
        self._num_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._num_edit)
        self._num_edit.setStyleSheet(EDIT_SS)
        self._num_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._num_edit))
        _add_field('Number', self._num_edit, stretch=2)

        self._rn_edit = QLineEdit(self.rn_value)
        self._rn_edit.setFixedHeight(FIELD_H)
        self._rn_edit.setFont(QFont('Segoe UI', _s(44)))
        self._rn_edit.setValidator(QRegExpValidator(QRegExp(r'\d{0,3}'), self._rn_edit))
        self._rn_edit.setStyleSheet(EDIT_SS)
        self._rn_edit.setInputMethodHints(Qt.ImhDigitsOnly)
        _add_field('RN', self._rn_edit, stretch=1)

        self._pc_btn = QPushButton()
        self._pc_btn.setFixedHeight(FIELD_H)
        self._pc_btn.setFont(QFont('Segoe UI', _s(44)))
        self._pc_btn.setAutoDefault(False)
        self._refresh_pc_btn()
        self._pc_btn.clicked.connect(self._on_pick_pc)
        _add_field('PC', self._pc_btn, stretch=1)

        c_lo.addLayout(fields_row)

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn        = _mk_btn('Cancel',  P['btn_sec'], h=72, fs=20, min_w=180)
        self._confirm_btn = _mk_btn('Confirm', P['btn_pri'], h=72, fs=20, min_w=180)
        cancel_btn.setAutoDefault(False)
        self._confirm_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        self._confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._confirm_btn)
        c_lo.addLayout(btn_row)

        lo.addWidget(content)
        self._trk_edit.returnPressed.connect(lambda: self._po_edit.setFocus())
        QTimer.singleShot(0, lambda: (self._trk_edit.setFocus(), self._trk_edit.selectAll()))

    def _refresh_pc_btn(self):
        filled = bool(self.pc_value)
        color = P['btn_pri'] if filled else P['subtitle']
        self._pc_btn.setText(self.pc_value if filled else '— pick —')
        self._pc_btn.setStyleSheet(
            f'QPushButton {{ background: white; color: {color};'
            f' border: {_s(3)}px solid {P["border"]}; border-radius: {_s(10)}px;'
            f' padding: {_s(10)}px {_s(18)}px; text-align: left; }}'
            f'QPushButton:hover {{ border-color: {P["btn_pri"]}; }}'
        )

    def _on_pick_pc(self):
        dlg = _PCPickerDialog(self.pc_value, self, light_theme=True)
        if dlg.exec_() == _PCPickerDialog.Accepted:
            self.pc_value = dlg.pc_value
            self._refresh_pc_btn()

    def _on_confirm(self):
        self.tracking_value = self._trk_edit.text().strip()
        self.po_value       = self._po_edit.text().strip()
        self.number_value   = self._num_edit.text().strip()
        self.rn_value       = self._rn_edit.text().strip()
        self.accept()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            w  = max(_s(820), int(pg.width() * 0.75))
            self.setFixedWidth(w)
            self.adjustSize()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + int(pg.height() * 0.08)
            self.move(x, y)
        return super().exec_()


# ── PO confirm dialog (floating card above keyboard) ─────────────────────────

class _POConfirmDialog(_DraggableDialog):
    """Floating card shown after OCR — split into 4 editable sub-fields."""

    def __init__(self, po_text: str = '', parent=None,
                 package_num: int = 0, tracking_tail: str = '',
                 autofill_rules: list = None, preset: dict = None,
                 retake_label: str = 'Retake', prev_po_parts: dict = None,
                 batch_info: tuple = ()):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        raw = po_text.strip().upper()
        _is_sg = (len(raw) == 9 and raw[:2] == 'SG' and raw[2:].isdigit())
        if _is_sg:
            self.po_value     = 'SG'
            self.number_value = raw[2:]
            self.rn_value     = ''
            self.pc_value     = ''
        else:
            self.po_value     = raw[0:2]   if len(raw) >= 2  else raw
            self.number_value = raw[2:7]   if len(raw) >= 7  else (raw[2:] if len(raw) > 2 else '')
            self.rn_value     = raw[7:10]  if len(raw) >= 10 else (raw[7:] if len(raw) > 7 else '')
            pc_cand           = raw[13:16] if len(raw) >= 16 else (raw[-3:] if len(raw) >= 3 else '')
            self.pc_value     = pc_cand if pc_cand in _PCPickerDialog._OPTIONS else ''
        if len(raw) == 7 and raw and (autofill_rules):
            first = raw[0]
            for rule in autofill_rules:
                if isinstance(rule, dict) and rule.get('prefix', '').upper() == first:
                    if not self.rn_value:
                        self.rn_value = rule.get('rn', '')
                    if not self.pc_value:
                        pc = rule.get('pc', '')
                        if pc in _PCPickerDialog._OPTIONS:
                            self.pc_value = pc
                    break
        if preset:
            self.po_value     = preset.get('po',     self.po_value)
            self.number_value = preset.get('number', self.number_value)
            self.rn_value     = preset.get('rn',     self.rn_value)
            self.pc_value     = preset.get('pc',     self.pc_value)
        self._retake_label  = retake_label
        self._prev_po_parts = prev_po_parts or {}
        self._batch_info    = batch_info
        self._build_ui(po_text, package_num, tracking_tail)

    def _build_ui(self, po_text: str, package_num: int, tracking_tail: str):
        p = _s(27)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(12))

        card = QWidget()
        card.setStyleSheet(f'background: #222222; border-radius: {_s(27)}px;')
        _shadow(card, blur=42, dy=12)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(_s(54), _s(42), _s(54), _s(42))
        lo.setSpacing(_s(24))

        info_parts = []
        if package_num:
            info_parts.append(f'Package  #{package_num}')
        if tracking_tail:
            info_parts.append(f'Tracking  ···{tracking_tail}')
        ctx_text = '   |   '.join(info_parts) if info_parts else 'Confirm or edit PO fields'
        status_lbl = QLabel(ctx_text)
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.setFont(QFont('Segoe UI', _s(27)))
        status_lbl.setStyleSheet('color: #CCCCCC; background: transparent;')
        lo.addWidget(status_lbl)

        FIELD_H = _s(100)
        EDIT_SS = (
            f'background: white; color: #1A1A1A;'
            f' border: {_s(3)}px solid #4ADE80;'
            f' border-radius: {_s(14)}px;'
            f' padding: {_s(10)}px {_s(16)}px;'
        )

        fields_row = QHBoxLayout()
        fields_row.setSpacing(_s(20))

        def _add_field(label_text, widget, stretch=1):
            col_w = QWidget()
            col_w.setStyleSheet('background: transparent;')
            cl = QVBoxLayout(col_w)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(_s(8))
            lbl = QLabel(label_text)
            lbl.setFont(QFont('Segoe UI', _s(26), QFont.Bold))
            lbl.setStyleSheet('color: #4ADE80; background: transparent;')
            cl.addWidget(lbl)
            cl.addWidget(widget)
            fields_row.addWidget(col_w, stretch)

        from PyQt5.QtCore import QRegExp
        from PyQt5.QtGui import QRegExpValidator

        self._po_edit = QLineEdit(self.po_value)
        self._po_edit.setFixedHeight(FIELD_H)
        self._po_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._po_edit)
        self._po_edit.setStyleSheet(EDIT_SS)
        self._po_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._po_edit))
        _add_field('PO', self._po_edit, stretch=1)

        self._num_edit = QLineEdit(self.number_value)
        self._num_edit.setFixedHeight(FIELD_H)
        self._num_edit.setFont(QFont('Segoe UI', _s(44)))
        _force_upper(self._num_edit)
        self._num_edit.setStyleSheet(EDIT_SS)
        self._num_edit.setValidator(QRegExpValidator(QRegExp(r'[A-Za-z0-9 ]*'), self._num_edit))
        _add_field('Number', self._num_edit, stretch=2)

        self._rn_edit = QLineEdit(self.rn_value)
        self._rn_edit.setFixedHeight(FIELD_H)
        self._rn_edit.setFont(QFont('Segoe UI', _s(44)))
        self._rn_edit.setValidator(QRegExpValidator(QRegExp(r'\d{0,3}'), self._rn_edit))
        self._rn_edit.setStyleSheet(EDIT_SS)
        self._rn_edit.setInputMethodHints(Qt.ImhDigitsOnly)
        _add_field('RN', self._rn_edit, stretch=1)

        self._pc_btn = QPushButton()
        self._pc_btn.setFixedHeight(FIELD_H)
        self._pc_btn.setFont(QFont('Segoe UI', _s(44)))
        self._pc_btn.setAutoDefault(False)
        self._refresh_pc_btn()
        self._pc_btn.clicked.connect(self._on_pick_pc)
        _add_field('PC', self._pc_btn, stretch=1)

        lo.addLayout(fields_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(27))
        retake_btn = QPushButton(self._retake_label)
        retake_btn.setFixedSize(_s(293), _s(122))
        retake_btn.setFont(QFont('Segoe UI', _s(32), QFont.Bold))
        retake_btn.setStyleSheet(f"""
            QPushButton {{ background: #555555; color: white; border: none; border-radius: {_s(18)}px; }}
            QPushButton:hover {{ background: #666666; }}
        """)
        retake_btn.setAutoDefault(False)
        retake_btn.clicked.connect(self.reject)
        confirm_text = f'Confirm  ({self._batch_info[0]} / {self._batch_info[1]})' if self._batch_info else 'Confirm'
        confirm_btn = QPushButton(confirm_text)
        confirm_btn.setFixedHeight(_s(122))
        confirm_btn.setMinimumWidth(_s(293))
        confirm_btn.setFont(QFont('Segoe UI', _s(32), QFont.Bold))
        confirm_btn.setStyleSheet(f"""
            QPushButton {{ background: #6BA547; color: white; border: none; border-radius: {_s(18)}px; }}
            QPushButton:hover {{ background: #5A9040; }}
        """)
        confirm_btn.setAutoDefault(False)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(retake_btn)
        btn_row.addStretch()
        if self._prev_po_parts:
            copy_prev_btn = QPushButton('Copy Previous PO')
            copy_prev_btn.setFixedHeight(_s(122))
            copy_prev_btn.setMinimumWidth(_s(330))
            copy_prev_btn.setFont(QFont('Segoe UI', _s(28), QFont.Bold))
            copy_prev_btn.setStyleSheet(f"""
                QPushButton {{ background: #3B82F6; color: white; border: none; border-radius: {_s(18)}px; }}
                QPushButton:hover {{ background: #2563EB; }}
            """)
            copy_prev_btn.setAutoDefault(False)
            copy_prev_btn.clicked.connect(self._on_copy_previous_po)
            btn_row.addWidget(copy_prev_btn)
        btn_row.addWidget(confirm_btn)
        lo.addLayout(btn_row)

        QTimer.singleShot(0, self._po_edit.setFocus)

    def _refresh_pc_btn(self):
        pc_color = '#4ADE80' if self.pc_value else '#888888'
        self._pc_btn.setText(self.pc_value if self.pc_value else '— pick —')
        self._pc_btn.setStyleSheet(
            f'QPushButton {{ background: #333333; color: {pc_color};'
            f' border: {_s(3)}px solid #4ADE80; border-radius: {_s(14)}px;'
            f' padding: {_s(10)}px {_s(22)}px; text-align: left; }}'
            f'QPushButton:hover {{ background: #444444; }}'
        )

    def _on_pick_pc(self):
        dlg = _PCPickerDialog(self.pc_value, self)
        if dlg.exec_() == _PCPickerDialog.Accepted:
            self.pc_value = dlg.pc_value
            self._refresh_pc_btn()

    def _on_copy_previous_po(self):
        self._po_edit.setText(self._prev_po_parts.get('po', ''))
        self._num_edit.setText(self._prev_po_parts.get('number', ''))
        self._rn_edit.setText(self._prev_po_parts.get('rn', ''))
        self.pc_value = self._prev_po_parts.get('pc', '')
        self._refresh_pc_btn()

    def _on_confirm(self):
        self.po_value     = self._po_edit.text().strip()
        self.number_value = self._num_edit.text().strip()
        self.rn_value     = self._rn_edit.text().strip()
        self.accept()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            w  = max(_s(720), int(pg.width() * 0.75))
            self.setFixedWidth(w)
            self.adjustSize()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + int(pg.height() * 0.08)
            self.move(x, y)
        return super().exec_()


# ── PC picker dialog ──────────────────────────────────────────────────────────

class _PCPickerDialog(_DraggableDialog):
    _OPTIONS = ['D11', 'D21', 'D31', 'D41', 'D51']

    def __init__(self, current_pc: str = '', parent=None, light_theme: bool = False):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.pc_value = current_pc
        self._build_ui(current_pc, light_theme)

    def _build_ui(self, current_pc: str, light_theme: bool):
        p = _s(20)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(p, p, p, p + _s(10))

        card = QWidget()
        if light_theme:
            card.setStyleSheet(
                f'background: {P["bg_start"]}; border-radius: {_s(24)}px;'
                f' border: {_s(2)}px solid {P["border"]};'
            )
        else:
            card.setStyleSheet(f'background: #222222; border-radius: {_s(24)}px;')
        _shadow(card, blur=40, dy=12)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(_s(40), _s(36), _s(40), _s(36))
        lo.setSpacing(_s(28))

        title = QLabel('Select PC')
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont('Segoe UI', _s(32), QFont.Bold))
        if light_theme:
            title.setStyleSheet(f'color: {P["title"]}; background: transparent;')
        else:
            title.setStyleSheet('color: #4ADE80; background: transparent;')
        lo.addWidget(title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(16))
        for opt in self._OPTIONS:
            is_cur = (opt == current_pc.upper())
            if light_theme:
                bg  = P['btn_pri'] if is_cur else P['panel']
                fg  = 'white'      if is_cur else P['text']
                hbg = P['btn_sec'] if is_cur else P['border']
                border = f'border: {_s(2)}px solid {P["border"]};'
            else:
                bg  = '#4ADE80' if is_cur else '#444444'
                fg  = '#1A1A1A' if is_cur else 'white'
                hbg = '#3BC870' if is_cur else '#555555'
                border = 'border: none;'
            btn = QPushButton(opt)
            btn.setFixedSize(_s(116), _s(96))
            btn.setFont(QFont('Segoe UI', _s(28), QFont.Bold))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {fg};
                    {border} border-radius: {_s(14)}px;
                }}
                QPushButton:hover   {{ background: {hbg}; }}
                QPushButton:pressed {{ background: {hbg}; }}
            """)
            btn.clicked.connect(lambda _, v=opt: self._pick(v))
            btn_row.addWidget(btn)
        lo.addLayout(btn_row)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setFixedHeight(_s(64))
        cancel_btn.setFont(QFont('Segoe UI', _s(22)))
        if light_theme:
            cancel_btn.setStyleSheet(
                f'QPushButton {{ background: transparent; color: {P["subtitle"]};'
                f' border: {_s(2)}px solid {P["border"]}; border-radius: {_s(10)}px; }}'
                f'QPushButton:hover {{ background: {P["border"]}; }}'
            )
        else:
            cancel_btn.setStyleSheet(
                'QPushButton { background: transparent; color: #888888;'
                ' border: 1px solid #555555; border-radius: ' + str(_s(10)) + 'px; }'
                'QPushButton:hover { background: #333333; color: #AAAAAA; }'
            )
        cancel_btn.clicked.connect(self.reject)
        lo.addWidget(cancel_btn)

    def _pick(self, value: str):
        self.pc_value = '' if value == self.pc_value else value
        self.accept()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            self.adjustSize()
            x = pg.x() + (pg.width()  - self.width())  // 2
            y = pg.y() + (pg.height() - self.height()) // 2
            self.move(x, y)
        return super().exec_()


# ── Settings password dialog ──────────────────────────────────────────────────

class _PasswordDialog(_DraggableDialog):
    """Password prompt shown before opening Settings from the main window."""

    def __init__(self, expected: str, parent=None):
        super().__init__(parent)
        self._expected = expected
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(_s(480))

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

        header = QWidget()
        header.setFixedHeight(_s(62))
        header.setStyleSheet(
            f'background: {P["title"]}; border-radius: {_s(20)}px {_s(20)}px 0 0;')
        h_lo = QHBoxLayout(header)
        h_lo.setContentsMargins(_s(26), 0, _s(26), 0)
        title_lbl = QLabel('Settings Access')
        title_lbl.setFont(QFont('Segoe UI', _s(20), QFont.Bold))
        title_lbl.setStyleSheet('color: white; background: transparent;')
        h_lo.addWidget(title_lbl)
        lo.addWidget(header)

        content = QWidget()
        content.setStyleSheet('background: transparent;')
        c_lo = QVBoxLayout(content)
        c_lo.setContentsMargins(_s(36), _s(28), _s(36), _s(28))
        c_lo.setSpacing(_s(16))

        self._input = QLineEdit()
        self._input.setEchoMode(QLineEdit.Password)
        self._input.setPlaceholderText('Enter password')
        self._input.setFont(QFont('Segoe UI', _s(18)))
        self._input.setFixedHeight(_s(54))
        self._input.setStyleSheet(
            f'QLineEdit {{ background: white; border: {_s(2)}px solid {P["border"]};'
            f' border-radius: {_s(10)}px; padding: 0 {_s(14)}px; color: {P["text"]}; }}'
            f'QLineEdit:focus {{ border-color: {P["btn_pri"]}; }}'
        )
        self._input.returnPressed.connect(self._on_confirm)
        c_lo.addWidget(self._input)

        self._err_lbl = QLabel('')
        self._err_lbl.setFont(QFont('Segoe UI', _s(15)))
        self._err_lbl.setStyleSheet('color: #EF4444; background: transparent;')
        self._err_lbl.setAlignment(Qt.AlignCenter)
        self._err_lbl.setFixedHeight(_s(24))
        c_lo.addWidget(self._err_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(16))
        cancel_btn = _mk_btn('Cancel',  P['btn_sec'], h=64, fs=18, min_w=160)
        ok_btn     = _mk_btn('Confirm', P['btn_pri'], h=64, fs=18, min_w=160)
        cancel_btn.setAutoDefault(False)
        ok_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        c_lo.addLayout(btn_row)
        lo.addWidget(content)

        QTimer.singleShot(0, self._input.setFocus)

    def _on_confirm(self):
        if self._input.text() == self._expected:
            self.accept()
        else:
            self._err_lbl.setText('Incorrect password.')
            self._input.clear()
            self._input.setFocus()

    def exec_(self):
        if self.parent():
            pg = self.parent().window().geometry()
            self.adjustSize()
            x = pg.x() + (pg.width()  - self.width())  // 2
            y = pg.y() + (pg.height() - self.height()) // 2
            self.move(x, y)
        return super().exec_()
