# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

easyocr_hiddenimports = collect_submodules('easyocr')
torchvision_hiddenimports = collect_submodules('torchvision')
skimage_hiddenimports = collect_submodules('skimage')
imageio_hiddenimports = collect_submodules('imageio')

easyocr_datas = collect_data_files('easyocr')
torchvision_datas = collect_data_files('torchvision')
skimage_datas = collect_data_files('skimage')
imageio_datas = collect_data_files('imageio')

torch_binaries = collect_dynamic_libs('torch')
torchvision_binaries = collect_dynamic_libs('torchvision')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=torch_binaries + torchvision_binaries,
    datas=[
        ('pdf_icon_512.png', '.'),
        ('pdf_tool.ico', '.'),
    ] + easyocr_datas + torchvision_datas + skimage_datas + imageio_datas,
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'fitz',
        'pymupdf',
        'PIL',
        'easyocr',
        'torch',
        'torchvision',
        'numpy',
        'cv2',
        'PIL.Image',
        'scipy',
        'pyclipper',
        'bidi',
        'bidi.algorithm',
        'skimage',
        'imageio',
        'google.genai',
        'google.genai.types',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        'httpx',
    ] + easyocr_hiddenimports + torchvision_hiddenimports + skimage_hiddenimports + imageio_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torchaudio', 'pandas', 'matplotlib', 'sklearn', 'scikit-learn', 'tensorflow', 'keras', 'transformers', 'IPython', 'notebook', 'jupyter', 'pytest', 'setuptools', 'pip', 'wheel', 'tkinter', '_tkinter', 'tcl', 'tk'],
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
