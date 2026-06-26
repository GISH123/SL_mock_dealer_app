# -*- mode: python ; coding: utf-8 -*-
import pathlib, shutil, os
import datetime

# timestamped exe name, e.g. DragonTigerWS_20250830
_ts = datetime.datetime.now().strftime("%Y%m%d")
_exe_base = f"DragonTigerWS_{_ts}"

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('..\\card_shown_ui', 'card_shown_ui')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_exe_base,
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
)
