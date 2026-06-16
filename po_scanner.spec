# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PO Scanner UI — light, fast rebuild.
Build command: pyinstaller po_scanner.spec --clean
Output: dist\po_scanner\po_scanner.exe + dist\po_scanner\settings.exe

NOTE: OCR Runtime is built separately via ocr_worker.spec.
      The main app communicates with ocr_runtime\ocr_core.exe via subprocess.
"""

from PyInstaller.utils.hooks import collect_all

cv2_datas,   cv2_bins,   cv2_hidden   = collect_all('cv2')
winrt_datas, winrt_bins, winrt_hidden = collect_all('winrt')

block_cipher = None

# ── Main app Analysis ────────────────────────────────────────────────────────

a1 = Analysis(
    ['po_scanner.py'],
    pathex=['.'],
    binaries=cv2_bins + winrt_bins,
    datas=[
        ('config', 'config'),
    ] + cv2_datas + winrt_datas,
    hiddenimports=[
        'openpyxl', 'openpyxl.styles',
        'yaml', 'requests',
        'cv2', 'numpy',
        'PyQt5.QtMultimedia',
        'winrt', 'winrt.windows', 'winrt.windows.media', 'winrt.windows.media.capture',
        'winrt.windows.media.capture.frames', 'winrt.windows.media.mediaproperties',
        'winrt.windows.graphics.imaging', 'winrt.windows.storage.streams',
        'winrt.windows.devices.enumeration', 'winrt.windows.foundation',
        'winrt.windows.foundation.collections',
    ] + cv2_hidden + winrt_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'paddle', 'paddleocr', 'paddlex',
        'rapidocr_onnxruntime', 'onnxruntime',
        'scipy', 'sklearn', 'skimage', 'imgaug', 'lmdb',
        'Cython', 'shapely', 'rapidfuzz', 'pyclipper', 'addict',
        'matplotlib', 'notebook', 'IPython', 'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Settings app Analysis ────────────────────────────────────────────────────

a2 = Analysis(
    ['settings_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config', 'config'),
    ],
    hiddenimports=[
        'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui',
        'yaml', 'requests', 'charset_normalizer', 'idna', 'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'notebook', 'IPython', 'tkinter',
        'paddle', 'paddleocr', 'paddlex', 'cv2', 'numpy', 'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Merge shared dependencies ────────────────────────────────────────────────

MERGE(
    (a1, 'po_scanner', 'po_scanner'),
    (a2, 'settings',   'settings'),
)

# ── PYZ archives ─────────────────────────────────────────────────────────────

pyz1 = PYZ(a1.pure, a1.zipped_data, cipher=block_cipher)
pyz2 = PYZ(a2.pure, a2.zipped_data, cipher=block_cipher)

# ── EXE targets ──────────────────────────────────────────────────────────────

exe1 = EXE(
    pyz1,
    a1.scripts,
    [],
    exclude_binaries=True,
    name='po_scanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='PO Scanner.ico',
)

exe2 = EXE(
    pyz2,
    a2.scripts,
    [],
    exclude_binaries=True,
    name='settings',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='setting.ico',
)

# ── Single COLLECT — both exes share _internal ───────────────────────────────

coll = COLLECT(
    exe1, a1.binaries, a1.zipfiles, a1.datas,
    exe2, a2.binaries, a2.zipfiles, a2.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='po_scanner',   # → dist\po_scanner\
)
