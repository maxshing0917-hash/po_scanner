# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OCR Worker (RapidOCR edition).
Build command: pyinstaller ocr_core.spec --clean
Output: dist\ocr_runtime\ocr_core.exe  (+ _internal\ with ONNX models)
"""

from PyInstaller.utils.hooks import collect_all

rapid_datas,  rapid_bins,  rapid_hidden  = collect_all('rapidocr_onnxruntime')
ort_datas,    ort_bins,    ort_hidden    = collect_all('onnxruntime')
cv2_datas,    cv2_bins,    cv2_hidden    = collect_all('cv2')
PIL_datas,    PIL_bins,    PIL_hidden    = collect_all('PIL')
clip_datas,   clip_bins,   clip_hidden   = collect_all('pyclipper')
shp_datas,    shp_bins,    shp_hidden    = collect_all('shapely')
zxing_datas,  zxing_bins,  zxing_hidden  = collect_all('zxingcpp')

block_cipher = None

a = Analysis(
    ['ocr_core.py'],
    pathex=['.'],
    binaries=ort_bins + cv2_bins + PIL_bins + zxing_bins,
    datas=[
        ('src', 'src'),
    ] + rapid_datas + ort_datas + cv2_datas + PIL_datas + clip_datas + shp_datas + zxing_datas,
    hiddenimports=[
        'rapidocr_onnxruntime',
        'onnxruntime', 'onnxruntime.capi',
        'pyclipper', 'shapely', 'shapely.geometry',
        'zxingcpp',
        'yaml', 'cv2', 'PIL', 'numpy',
    ] + rapid_hidden + ort_hidden + cv2_hidden + PIL_hidden + clip_hidden + shp_hidden + zxing_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'paddle', 'paddleocr', 'paddlex',
        'matplotlib', 'notebook', 'IPython', 'tkinter',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'winrt',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ocr_core',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon='PO Scanner.ico',
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ocr_runtime',   # → dist\ocr_runtime\
)
