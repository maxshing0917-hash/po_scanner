#!/usr/bin/env python3
"""
PO Scanner — Settings
Lightweight GUI for editing user-facing options in config.yaml.
Technical parameters that affect detection quality are intentionally hidden.
"""

import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox, QSpinBox,
    QGroupBox, QFileDialog, QMessageBox, QStatusBar, QSizePolicy,
    QScrollArea, QFrame, QListWidget, QListWidgetItem, QDialog,
)
from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import QFont, QIcon

import yaml  # PyYAML (already a project dependency)

# ── DPI-relative scale ────────────────────────────────────────────────────────

_S: float = 1.0

def _s(px) -> int:
    return max(1, int(round(px * _S)))


# ── Config location ───────────────────────────────────────────────────────────
def _base_dir() -> str:
    """Return the directory that contains the config/ folder."""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(os.path.join(meipass, 'config')):
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_base_dir(), 'config', 'config.yaml')


def load_config() -> dict:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_config(cfg: dict):
    """Write config back. Uses yaml.dump — preserves values, strips inline comments."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False)



# ── Stylesheet ────────────────────────────────────────────────────────────────

def _make_style() -> str:
    return f"""
QMainWindow, QWidget#root {{
    background-color: #FFF8F0;
}}
QScrollArea, QWidget#scroll_content {{
    background-color: #FFF8F0;
    border: none;
}}
QGroupBox {{
    font-weight: bold;
    font-size: {_s(32)}px;
    border: {_s(4)}px solid #D4B896;
    border-radius: {_s(20)}px;
    margin-top: {_s(30)}px;
    padding-top: {_s(15)}px;
    background-color: #FFFCF8;
    color: #5C3D2A;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {_s(30)}px;
    padding: 0 {_s(15)}px;
}}
QLabel {{
    color: #4a3728;
    min-width: {_s(250)}px;
    font-size: {_s(32)}px;
}}
QLabel#section_hint {{
    color: #9B8877;
    font-size: {_s(28)}px;
    font-style: italic;
    min-width: 0;
}}
QLineEdit {{
    border: {_s(3)}px solid #C8A882;
    border-radius: {_s(15)}px;
    padding: {_s(12)}px {_s(20)}px;
    background: white;
    color: #3a2a1e;
    font-size: {_s(32)}px;
}}
QLineEdit:focus {{ border: {_s(4)}px solid #8B6347; }}
QLineEdit:disabled {{ background: #F5EDE3; color: #9B8877; }}
QComboBox {{
    border: {_s(3)}px solid #C8A882;
    border-radius: {_s(15)}px;
    padding: {_s(12)}px {_s(20)}px;
    background: white;
    color: #3a2a1e;
    font-size: {_s(32)}px;
}}
QComboBox::drop-down {{ border: none; width: {_s(50)}px; }}
QSpinBox {{
    border: {_s(3)}px solid #C8A882;
    border-radius: {_s(15)}px;
    padding: {_s(12)}px {_s(20)}px;
    background: white;
    color: #3a2a1e;
    font-size: {_s(32)}px;
    max-width: {_s(250)}px;
}}
QCheckBox {{ font-size: {_s(32)}px; color: #4a3728; spacing: {_s(20)}px; }}
QCheckBox::indicator {{
    width: {_s(40)}px; height: {_s(40)}px;
    border: {_s(4)}px solid #C8A882;
    border-radius: {_s(8)}px;
    background: white;
}}
QCheckBox::indicator:checked {{
    background-color: #7B9E6B;
    border-color: #7B9E6B;
    image: none;
}}
QPushButton {{
    border-radius: {_s(15)}px;
    padding: {_s(15)}px {_s(40)}px;
    font-size: {_s(32)}px;
    font-weight: bold;
}}
QPushButton#saveBtn {{
    background-color: #7B9E6B;
    color: white;
    border: none;
    padding: {_s(20)}px {_s(90)}px;
    font-size: {_s(35)}px;
}}
QPushButton#saveBtn:hover  {{ background-color: #6A8D5A; }}
QPushButton#cancelBtn {{
    background-color: #C8A882;
    color: white;
    border: none;
    padding: {_s(20)}px {_s(60)}px;
}}
QPushButton#cancelBtn:hover {{ background-color: #B09070; }}
QPushButton#browseBtn, QPushButton#refreshBtn {{
    background-color: #EAD9C6;
    color: #4a3728;
    border: {_s(3)}px solid #C8A882;
    padding: {_s(12)}px {_s(35)}px;
    font-weight: normal;
}}
QPushButton#browseBtn:hover, QPushButton#refreshBtn:hover {{
    background-color: #D4B896;
}}
QPushButton#refreshBtn:disabled {{ color: #9B8877; }}
QStatusBar {{
    border-top: {_s(3)}px solid #D4B896;
    background: #FFF0E0;
    color: #6B4C35;
    font-size: {_s(30)}px;
    padding: {_s(5)}px {_s(20)}px;
}}
QMessageBox QLabel {{ min-width: 0; font-weight: normal; }}
QMessageBox QPushButton {{ font-weight: normal; padding: {_s(12)}px {_s(50)}px; min-width: 0; }}
QListWidget {{
    border: {_s(3)}px solid #C8A882;
    border-radius: {_s(15)}px;
    background: white;
    font-size: {_s(30)}px;
    color: #3a2a1e;
}}
QListWidget::item {{ padding: {_s(10)}px {_s(16)}px; }}
QListWidget::item:selected {{ background: #EAD9C6; color: #3a2a1e; }}
QPushButton#removeBtn {{
    background-color: #C0392B;
    color: white;
    border: none;
    padding: {_s(12)}px {_s(35)}px;
    font-weight: normal;
}}
QPushButton#removeBtn:hover {{ background-color: #A93226; }}
QPushButton#removeBtn:disabled {{ background-color: #D4B896; }}
QPushButton#generateBtn {{
    background-color: #5B8DB8;
    color: white;
    border: none;
    padding: {_s(15)}px {_s(50)}px;
    font-size: {_s(32)}px;
    font-weight: bold;
}}
QPushButton#generateBtn:hover {{ background-color: #4A7AA0; }}
QPushButton#generateBtn:disabled {{ background-color: #9BB8D0; }}
QScrollBar:vertical {{
    background: #F0E8DC;
    width: {_s(28)}px;
    border-radius: {_s(14)}px;
    margin: {_s(4)}px {_s(2)}px;
}}
QScrollBar::handle:vertical {{
    background: #C8A882;
    border-radius: {_s(12)}px;
    min-height: {_s(60)}px;
}}
QScrollBar::handle:vertical:hover {{ background: #B09070; }}
QScrollBar::handle:vertical:pressed {{ background: #9B8877; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


# ── Drag-to-scroll helper ─────────────────────────────────────────────────────
class _DragScroll(QObject):
    """Click-and-drag anywhere on the scroll area viewport to pan vertically."""
    def __init__(self, scroll_area):
        super().__init__(scroll_area)
        self._scroll = scroll_area
        self._active = False
        self._start_y = 0
        self._start_val = 0
        vp = scroll_area.viewport()
        vp.setCursor(Qt.OpenHandCursor)
        vp.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self._scroll.viewport():
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._active = True
            self._start_y = event.pos().y()
            self._start_val = self._scroll.verticalScrollBar().value()
            obj.setCursor(Qt.ClosedHandCursor)
            return True
        if t == QEvent.MouseMove and self._active:
            delta = event.pos().y() - self._start_y
            self._scroll.verticalScrollBar().setValue(self._start_val - delta)
            return True
        if t == QEvent.MouseButtonRelease and self._active:
            self._active = False
            obj.setCursor(Qt.OpenHandCursor)
            return True
        return False


# ── PO Auto-fill rule dialog ──────────────────────────────────────────────────
class _AutofillRuleDialog(QDialog):
    _PC_OPTIONS = ['D11', 'D21', 'D31', 'D41', 'D51']
    _VALID_PREFIXES = ['A', 'W', 'S', 'I', 'B', 'X', 'N']

    def __init__(self, rule: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Rule' if rule is None else 'Edit Rule')
        self.setModal(True)
        self.setMinimumWidth(_s(480))
        self._rule = rule or {}
        self._build_ui()

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setSpacing(_s(24))
        lo.setContentsMargins(_s(32), _s(32), _s(32), _s(32))

        def _row(label_text, widget):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(_s(220))
            row.addWidget(lbl)
            row.addWidget(widget)
            lo.addLayout(row)

        self._prefix_combo = QComboBox()
        self._prefix_combo.addItems(self._VALID_PREFIXES)
        saved = self._rule.get('prefix', '')
        if saved in self._VALID_PREFIXES:
            self._prefix_combo.setCurrentText(saved)
        _row('PO first letter', self._prefix_combo)

        self._rn_edit = QLineEdit(self._rule.get('rn', ''))
        self._rn_edit.setPlaceholderText('e.g. 000')
        self._rn_edit.setMaxLength(3)
        _row('RN  (3 digits)', self._rn_edit)

        self._pc_combo = QComboBox()
        self._pc_combo.addItems(self._PC_OPTIONS)
        saved_pc = self._rule.get('pc', '')
        if saved_pc in self._PC_OPTIONS:
            self._pc_combo.setCurrentText(saved_pc)
        _row('PC', self._pc_combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton('Cancel')
        cancel.setObjectName('cancelBtn')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('OK')
        ok.setObjectName('saveBtn')
        ok.clicked.connect(self._on_ok)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lo.addLayout(btn_row)

    def _on_ok(self):
        rn = self._rn_edit.text().strip()
        if not (len(rn) == 3 and rn.isdigit()):
            QMessageBox.warning(self, 'Invalid Input', 'RN must be exactly 3 digits (e.g. 000).')
            return
        self.accept()

    def get_rule(self) -> dict:
        return {
            'prefix': self._prefix_combo.currentText(),
            'rn': self._rn_edit.text().strip(),
            'pc': self._pc_combo.currentText(),
        }


# ── Main window ───────────────────────────────────────────────────────────────
class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PO Scanner — Settings')
        self.setMinimumWidth(_s(1300))
        self.resize(_s(1500), _s(1000))
        self.setStyleSheet(_make_style())
        self._fetcher = None

        try:
            self.cfg = load_config()
        except FileNotFoundError:
            QMessageBox.critical(self, 'Error',
                f'Config file not found:\n{CONFIG_PATH}')
            sys.exit(1)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot read config:\n{e}')
            sys.exit(1)

        self._dirty = False
        self._build_ui()
        self._load_values()
        self._connect_dirty_signals()
        sb = QStatusBar()
        self.setStatusBar(sb)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Scroll area wrapper (in case window is small)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.setCentralWidget(scroll)
        self._drag_scroll = _DragScroll(scroll)

        content = QWidget()
        content.setObjectName('scroll_content')
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setSpacing(_s(35))
        root.setContentsMargins(_s(45), _s(45), _s(45), _s(45))

        root.addWidget(self._build_paths_group())
        root.addWidget(self._build_blacklist_group())
        root.addWidget(self._build_autofill_group())
        root.addWidget(self._build_ocr_group())
        root.addWidget(self._build_camera_group())
        root.addWidget(self._build_excel_group())
        root.addSpacing(20)
        root.addLayout(self._build_buttons())
        root.addStretch()

    def _build_paths_group(self) -> QGroupBox:
        g = QGroupBox('📁  File Paths')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(25))

        # CSV save folder
        csv_row = QHBoxLayout()
        csv_row.addWidget(QLabel('CSV save folder'))
        self.csv_folder = QLineEdit()
        self.csv_folder.setPlaceholderText('C:/Users/.../Desktop')
        csv_row.addWidget(self.csv_folder)
        btn_csv = QPushButton('📂  Browse')
        btn_csv.setObjectName('browseBtn')
        btn_csv.clicked.connect(self._browse_csv_folder)
        csv_row.addWidget(btn_csv)
        lay.addLayout(csv_row)

        hint = QLabel('CSV files (e.g. PO_May_2026.csv) will be saved to this folder')
        hint.setObjectName('section_hint')
        lay.addWidget(hint)

        return g

    def _build_blacklist_group(self) -> QGroupBox:
        g = QGroupBox('🚫  PO Blacklist')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(20))

        hint = QLabel('Words that match PO rules but are not POs (e.g. person names) — added entries are automatically filtered during scanning')
        hint.setObjectName('section_hint')
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.blacklist_widget = QListWidget()
        self.blacklist_widget.setFixedHeight(_s(220))
        self.blacklist_widget.itemSelectionChanged.connect(self._on_blacklist_select)
        lay.addWidget(self.blacklist_widget)

        add_row = QHBoxLayout()
        self.blacklist_input = QLineEdit()
        self.blacklist_input.setPlaceholderText('Enter word to filter, e.g. SANCHEZ')
        self.blacklist_input.returnPressed.connect(self._blacklist_add)
        add_row.addWidget(self.blacklist_input)

        btn_add = QPushButton('＋  Add')
        btn_add.setObjectName('browseBtn')
        btn_add.clicked.connect(self._blacklist_add)
        add_row.addWidget(btn_add)

        self.btn_remove = QPushButton('✕  Remove')
        self.btn_remove.setObjectName('removeBtn')
        self.btn_remove.setEnabled(False)
        self.btn_remove.clicked.connect(self._blacklist_remove)
        add_row.addWidget(self.btn_remove)

        lay.addLayout(add_row)
        return g

    def _blacklist_add(self):
        word = self.blacklist_input.text().strip().upper()
        if not word:
            return
        existing = [self.blacklist_widget.item(i).text()
                    for i in range(self.blacklist_widget.count())]
        if word not in existing:
            self.blacklist_widget.addItem(word)
            self._mark_dirty()
        self.blacklist_input.clear()

    def _blacklist_remove(self):
        for item in self.blacklist_widget.selectedItems():
            self.blacklist_widget.takeItem(self.blacklist_widget.row(item))
        self._mark_dirty()

    def _on_blacklist_select(self):
        self.btn_remove.setEnabled(bool(self.blacklist_widget.selectedItems()))

    def _build_autofill_group(self) -> QGroupBox:
        g = QGroupBox('⚡  PO Auto-fill Rules')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(20))

        hint = QLabel(
            'When a 7-character PO is scanned, auto-fill RN and PC based on its first letter.'
        )
        hint.setObjectName('section_hint')
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.autofill_list = QListWidget()
        self.autofill_list.setFixedHeight(_s(220))
        self.autofill_list.itemSelectionChanged.connect(self._on_autofill_select)
        lay.addWidget(self.autofill_list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton('＋  Add')
        btn_add.setObjectName('browseBtn')
        btn_add.clicked.connect(self._autofill_add)
        btn_row.addWidget(btn_add)

        self.btn_autofill_edit = QPushButton('✎  Edit')
        self.btn_autofill_edit.setObjectName('browseBtn')
        self.btn_autofill_edit.setEnabled(False)
        self.btn_autofill_edit.clicked.connect(self._autofill_edit)
        btn_row.addWidget(self.btn_autofill_edit)

        self.btn_autofill_remove = QPushButton('✕  Remove')
        self.btn_autofill_remove.setObjectName('removeBtn')
        self.btn_autofill_remove.setEnabled(False)
        self.btn_autofill_remove.clicked.connect(self._autofill_remove)
        btn_row.addWidget(self.btn_autofill_remove)

        btn_row.addStretch()
        lay.addLayout(btn_row)
        return g

    @staticmethod
    def _autofill_item_text(rule: dict) -> str:
        return f"[{rule.get('prefix','?')}]  →  RN: {rule.get('rn','?')}  |  PC: {rule.get('pc','?')}"

    def _on_autofill_select(self):
        has = bool(self.autofill_list.selectedItems())
        self.btn_autofill_edit.setEnabled(has)
        self.btn_autofill_remove.setEnabled(has)

    def _autofill_add(self):
        dlg = _AutofillRuleDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        rule = dlg.get_rule()
        # disallow duplicate prefix
        for i in range(self.autofill_list.count()):
            existing = self.autofill_list.item(i).data(Qt.UserRole)
            if existing.get('prefix') == rule['prefix']:
                QMessageBox.warning(self, 'Duplicate', f"A rule for prefix '{rule['prefix']}' already exists. Edit it instead.")
                return
        item = QListWidgetItem(self._autofill_item_text(rule))
        item.setData(Qt.UserRole, rule)
        self.autofill_list.addItem(item)
        self._mark_dirty()

    def _autofill_edit(self):
        items = self.autofill_list.selectedItems()
        if not items:
            return
        item = items[0]
        dlg = _AutofillRuleDialog(rule=item.data(Qt.UserRole), parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        rule = dlg.get_rule()
        # disallow duplicate prefix on another row
        for i in range(self.autofill_list.count()):
            other = self.autofill_list.item(i)
            if other is not item and other.data(Qt.UserRole).get('prefix') == rule['prefix']:
                QMessageBox.warning(self, 'Duplicate', f"A rule for prefix '{rule['prefix']}' already exists.")
                return
        item.setText(self._autofill_item_text(rule))
        item.setData(Qt.UserRole, rule)
        self._mark_dirty()

    def _autofill_remove(self):
        for item in self.autofill_list.selectedItems():
            self.autofill_list.takeItem(self.autofill_list.row(item))
        self._mark_dirty()

    def _build_ocr_group(self) -> QGroupBox:
        g = QGroupBox('🔍  OCR')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(25))

        self.gpu_check = QCheckBox('Use GPU  (requires CUDA — leave off if unsure)')
        lay.addWidget(self.gpu_check)

        return g

    def _build_camera_group(self) -> QGroupBox:
        g = QGroupBox('📷  Camera')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(25))

        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel('Default device'))
        self.cam_combo = QComboBox()
        self.cam_combo.setMinimumWidth(_s(500))
        cam_row.addWidget(self.cam_combo)
        self._detect_btn = QPushButton('↻  Detect')
        self._detect_btn.setObjectName('refreshBtn')
        self._detect_btn.clicked.connect(self._detect_cameras)
        cam_row.addWidget(self._detect_btn)
        cam_row.addStretch()
        lay.addLayout(cam_row)

        hint = QLabel('Click Detect to scan available cameras')
        hint.setObjectName('section_hint')
        lay.addWidget(hint)

        return g

    def _build_excel_group(self) -> QGroupBox:
        g = QGroupBox('📅  Generate Yearly Excel')
        lay = QVBoxLayout(g)
        lay.setSpacing(_s(25))

        hint = QLabel('Select a template .xlsm, then generate Trial JAN–DEC files for a given year.')
        hint.setObjectName('section_hint')
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # Template file
        tpl_row = QHBoxLayout()
        tpl_row.addWidget(QLabel('Template (.xlsm)'))
        self.excel_template = QLineEdit()
        self.excel_template.setPlaceholderText(r'e.g. C:\PO Scanner\Template\Trial Template.xlsm')
        tpl_row.addWidget(self.excel_template)
        btn_tpl = QPushButton('📂  Browse')
        btn_tpl.setObjectName('browseBtn')
        btn_tpl.clicked.connect(self._browse_excel_template)
        tpl_row.addWidget(btn_tpl)
        lay.addLayout(tpl_row)

        # Output folder
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel('Output folder'))
        self.excel_out_folder = QLineEdit()
        self.excel_out_folder.setPlaceholderText(r'e.g. C:\PO Scanner\Template')
        out_row.addWidget(self.excel_out_folder)
        btn_out = QPushButton('📂  Browse')
        btn_out.setObjectName('browseBtn')
        btn_out.clicked.connect(self._browse_excel_output)
        out_row.addWidget(btn_out)
        lay.addLayout(out_row)

        # Year + Generate button
        from datetime import date as _date
        gen_row = QHBoxLayout()
        gen_row.addWidget(QLabel('Year'))
        self.excel_year = QSpinBox()
        _cur = _date.today().year
        self.excel_year.setRange(_cur - 1, _cur + 5)
        self.excel_year.setValue(_cur)
        self.excel_year.setMinimumWidth(_s(220))
        gen_row.addWidget(self.excel_year)
        gen_row.addStretch()
        btn_gen = QPushButton('⚡  Generate 12 Files')
        btn_gen.setObjectName('generateBtn')
        btn_gen.clicked.connect(self._generate_excel)
        gen_row.addWidget(btn_gen)
        lay.addLayout(gen_row)

        return g

    def _browse_excel_template(self):
        start = self.excel_template.text() or r'C:\PO Scanner\Template'
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Template .xlsm', start,
            'Excel Macro-Enabled Workbook (*.xlsm)'
        )
        if path:
            self.excel_template.setText(os.path.normpath(path))

    def _browse_excel_output(self):
        start = self.excel_out_folder.text() or r'C:\PO Scanner\Template'
        folder = QFileDialog.getExistingDirectory(self, 'Choose Output Folder', start)
        if folder:
            self.excel_out_folder.setText(os.path.normpath(folder))

    def _generate_excel(self):
        import shutil

        _MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                   'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

        template = self.excel_template.text().strip()
        out_folder = self.excel_out_folder.text().strip()
        year = self.excel_year.value()

        if not template:
            QMessageBox.warning(self, 'Missing Template', 'Please select a .xlsm template file.')
            return
        if not os.path.isfile(template):
            QMessageBox.warning(self, 'Template Not Found', f'File not found:\n{template}')
            return
        if not template.lower().endswith('.xlsm'):
            QMessageBox.warning(self, 'Invalid File', 'Template must be a .xlsm file.')
            return
        if not out_folder:
            QMessageBox.warning(self, 'Missing Output Folder', 'Please select an output folder.')
            return

        os.makedirs(out_folder, exist_ok=True)

        targets = [os.path.join(out_folder, f'Trial {m} {year}.xlsm') for m in _MONTHS]
        existing = [t for t in targets if os.path.exists(t)]
        if existing:
            names = '\n'.join(os.path.basename(t) for t in existing)
            reply = QMessageBox.question(
                self, 'Files Already Exist',
                f'These files already exist and will be overwritten:\n\n{names}\n\nContinue?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        errors = []
        for m, dest in zip(_MONTHS, targets):
            try:
                shutil.copy2(template, dest)
            except Exception as e:
                errors.append(f'{m}: {e}')

        if errors:
            QMessageBox.warning(self, 'Partial Failure',
                'Some files could not be created:\n' + '\n'.join(errors))
        else:
            self.statusBar().showMessage(f'✓  12 Excel files generated for {year}', 5000)
            QMessageBox.information(self, 'Done',
                f'12 files generated in:\n{out_folder}')

    def _detect_cameras(self):
        import asyncio
        self._detect_btn.setEnabled(False)
        self._detect_btn.setText('Scanning…')
        QApplication.processEvents()

        found = []
        try:
            import winrt.windows.media.capture.frames as wmcf
            async def _enum():
                groups = await wmcf.MediaFrameSourceGroup.find_all_async()
                return [(i, g.display_name) for i, g in enumerate(groups)]
            loop = asyncio.new_event_loop()
            found = loop.run_until_complete(_enum())
            loop.close()
        except Exception as e:
            self.statusBar().showMessage(f'Camera scan failed: {e}', 4000)

        self._detect_btn.setEnabled(True)
        self._detect_btn.setText('↻  Detect')

        current_idx = self.cfg.get('camera', {}).get('default_index', 0)
        self.cam_combo.clear()
        if found:
            for i, name in found:
                self.cam_combo.addItem(f'[{i}] {name}', userData=i)
            for j in range(self.cam_combo.count()):
                if self.cam_combo.itemData(j) == current_idx:
                    self.cam_combo.setCurrentIndex(j)
                    break
        else:
            self.cam_combo.addItem('No cameras found', userData=0)
        self.statusBar().showMessage(f'Found {len(found)} camera(s)', 3000)

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton('Cancel')
        cancel.setObjectName('cancelBtn')
        cancel.clicked.connect(self.close)
        row.addWidget(cancel)
        save = QPushButton('💾  Save')
        save.setObjectName('saveBtn')
        save.clicked.connect(self._save)
        row.addWidget(save)
        return row

    # ── Dirty tracking ───────────────────────────────────────────────────────
    def _mark_dirty(self):
        self._dirty = True

    def _connect_dirty_signals(self):
        self.csv_folder.textChanged.connect(self._mark_dirty)
        self.gpu_check.toggled.connect(self._mark_dirty)
        self.cam_combo.currentIndexChanged.connect(self._mark_dirty)
        self.excel_template.textChanged.connect(self._mark_dirty)
        self.excel_out_folder.textChanged.connect(self._mark_dirty)

    def bring_to_front(self):
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        if not self._dirty:
            event.accept()
            return
        reply = QMessageBox.question(
            self, 'Unsaved Changes',
            'You have unsaved changes.\nSave before closing?',
            QMessageBox.Save | QMessageBox.Discard,
            QMessageBox.Save,
        )
        if reply == QMessageBox.Save:
            self._save()
        event.accept()

    # ── Load current values from config ──────────────────────────────────────
    def _load_values(self):
        cfg = self.cfg

        # Paths
        csv = cfg.get('csv', {})
        self.csv_folder.setText(str(csv.get('folder', '')))

        # Blacklist
        blacklist = cfg.get('extraction', {}).get('po_blacklist', [])
        self.blacklist_widget.clear()
        for word in blacklist:
            self.blacklist_widget.addItem(str(word).upper())

        # Auto-fill rules
        self.autofill_list.clear()
        for rule in cfg.get('po_autofill', []):
            if not isinstance(rule, dict):
                continue
            item = QListWidgetItem(self._autofill_item_text(rule))
            item.setData(Qt.UserRole, dict(rule))
            self.autofill_list.addItem(item)

        # OCR
        ocr = cfg.get('ocr', {})
        self.gpu_check.setChecked(bool(ocr.get('use_gpu', False)))

        # Camera — populate combo with saved index as placeholder until Detect is clicked
        cam = cfg.get('camera', {})
        saved_idx = cam.get('default_index', 0)
        self.cam_combo.clear()
        self.cam_combo.addItem(f'Camera {saved_idx} (saved)', userData=saved_idx)

        # Excel generator
        excel_gen = cfg.get('excel_generator', {})
        self.excel_template.setText(str(excel_gen.get('template_path', '')))
        self.excel_out_folder.setText(str(excel_gen.get('output_folder', r'C:\PO Scanner\Template')))


    # ── File browse ───────────────────────────────────────────────────────────
    def _browse_csv_folder(self):
        start = self.csv_folder.text() or os.path.expanduser('~')
        folder = QFileDialog.getExistingDirectory(self, 'Choose CSV save folder', start)
        if folder:
            self.csv_folder.setText(os.path.normpath(folder))

    # ── Save ──────────────────────────────────────────────────────────────────
    def _save(self):
        cfg = self.cfg
        # --- Paths ---
        if 'csv' not in cfg:
            cfg['csv'] = {}
        cfg['csv']['folder'] = self.csv_folder.text().strip()

        # --- Blacklist ---
        if 'extraction' not in cfg:
            cfg['extraction'] = {}
        cfg['extraction']['po_blacklist'] = [
            self.blacklist_widget.item(i).text()
            for i in range(self.blacklist_widget.count())
        ]

        # --- Auto-fill rules ---
        cfg['po_autofill'] = [
            self.autofill_list.item(i).data(Qt.UserRole)
            for i in range(self.autofill_list.count())
        ]

        # --- OCR ---
        if 'ocr' not in cfg:
            cfg['ocr'] = {}
        cfg['ocr']['language'] = 'en'
        cfg['ocr']['use_gpu']  = self.gpu_check.isChecked()

        # --- Camera ---
        if 'camera' not in cfg:
            cfg['camera'] = {}
        cam_index = self.cam_combo.currentData() or 0
        cfg['camera']['default_index'] = cam_index

        # --- Excel generator ---
        if 'excel_generator' not in cfg:
            cfg['excel_generator'] = {}
        cfg['excel_generator']['template_path'] = self.excel_template.text().strip()
        cfg['excel_generator']['output_folder']  = self.excel_out_folder.text().strip()
        # sync camera_state.json so the main app picks up the new index immediately
        try:
            import json
            state_path = os.path.join(_base_dir(), 'config', 'camera_state.json')
            with open(state_path, 'w') as f:
                json.dump({'cam_index': cam_index}, f)
        except Exception:
            pass

        try:
            save_config(cfg)
            self._dirty = False
            self.statusBar().showMessage('✓  Settings saved', 4000)
            QMessageBox.information(
                self, 'Saved',
                'Settings saved successfully.\n\nRestart PO Scanner to apply changes.')
        except Exception as e:
            QMessageBox.critical(self, 'Save Failed', f'Could not write config:\n{e}')


# ── Entry point ───────────────────────────────────────────────────────────────
_INSTANCE_KEY = 'POScannerSettings_SingleInstance_v1'

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName('PO Scanner Settings')

    # Single-instance check
    _sock = QLocalSocket()
    _sock.connectToServer(_INSTANCE_KEY)
    if _sock.waitForConnected(500):
        _sock.write(b'RAISE')
        _sock.flush()
        _sock.waitForBytesWritten(1000)
        _sock.disconnectFromServer()
        sys.exit(0)

    global _S
    _S = QApplication.primaryScreen().availableGeometry().height() / 1080

    win = SettingsWindow()
    screen = app.primaryScreen().availableGeometry()
    win.move(
        screen.x() + (screen.width()  - win.width())  // 2,
        screen.y() + (screen.height() - win.height()) // 2,
    )
    win.show()

    _server = QLocalServer(app)
    QLocalServer.removeServer(_INSTANCE_KEY)
    _server.listen(_INSTANCE_KEY)

    def _on_new_connection():
        conn = _server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(500)
            conn.close()
            win.bring_to_front()

    _server.newConnection.connect(_on_new_connection)

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
