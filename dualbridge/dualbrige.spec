# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# NOTE: PyInstaller executes .spec via exec(); __file__ may be undefined.
# SPECPATH is provided by PyInstaller and points to the folder containing this spec.
project_dir = os.path.abspath(globals().get("SPECPATH", os.getcwd()))

hiddenimports = []
hiddenimports += collect_submodules('websockets')
# python-dotenv is optional at runtime, but recommended for .env support.
hiddenimports += collect_submodules('dotenv')

# Bundle a default .env into the dist folder (onedir build).
datas = [(os.path.join(project_dir, '.env'), '.')]


a = Analysis(
    ['dualbrige.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    name='dualbrige',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dualbrige',
)
