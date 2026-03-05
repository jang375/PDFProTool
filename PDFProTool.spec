# -*- mode: python ; coding: utf-8 -*-
import os

EASYOCR_MODEL_DIR = os.path.expanduser('~/.EasyOCR/model')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('pdf_icon_512.png', '.'),
        ('pdf_tool.ico', '.'),
        (EASYOCR_MODEL_DIR, '.EasyOCR/model'),
    ],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'fitz', 'pymupdf', 'PIL', 'easyocr', 'torch', 'torchvision', 'numpy', 'cv2', 'PIL.Image', 'scipy', 'pyclipper', 'bidi', 'bidi.algorithm', 'skimage', 'imageio', 'google.genai', 'google.genai.types', 'google.auth', 'google.auth.transport', 'google.auth.transport.requests', 'httpx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torchaudio', 'pandas', 'matplotlib', 'sklearn', 'scikit-learn', 'tensorflow', 'keras', 'transformers', 'sympy', 'IPython', 'notebook', 'jupyter', 'pytest', 'setuptools', 'pip', 'wheel', 'tkinter', '_tkinter', 'tcl', 'tk'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDFProTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['pdf_tool.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDFProTool',
)
