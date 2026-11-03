# -*- mode: python ; coding: utf-8 -*-

datas = [
    ('config/detection_thresholds.json', 'config'),
    ('config/bank_field_mapping.json', 'config'),
    ('bankfusion.db', '.'),
]

a = Analysis(
    ['desktop_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'sqlalchemy.ext.baked',
        'sqlalchemy.sql.default_comparator',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'utils',
        'utils.path_resolver',
        'database',
        'database.migrations',
        'fraud_detection.demo_auto_block_scenario',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'tkinter',
        'matplotlib',
        'torch',
        'torchvision',
        'torchaudio',
        'scipy',
        'IPython',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BankFusion',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BankFusion',
)
