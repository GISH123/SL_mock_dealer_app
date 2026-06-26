# full_build.spec

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(os.getcwd())
env_file = str(ROOT / "config.env")

block_cipher = None
hiddenimports = collect_submodules("utils")

common_options = dict(
    pathex=[str(ROOT)],
    hiddenimports=hiddenimports,
    runtime_hooks=[],
    cipher=block_cipher,
    noarchive=False
)

def build_component(name, script):
    a = Analysis(
        [script],
        **common_options,
        binaries=[],
        datas=[],
        hookspath=[],
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=name
    )
    return coll

executables = []

# ─────────────────────────────────────────────
# Each component gets built separately
# ─────────────────────────────────────────────
for name, script in [
    ("message_hub_exec",        "message_hub/main.py"),
    ("fm_gateway_exec",         "FM_gateway/main_http.py"),
    ("fm_gateway_https_exec",   "FM_gateway/main_https.py"),   # ✅ added HTTPS FM Gateway
    ("dvr_gateway_http_exec",   "DVR_gateway/main_http.py"),
    ("dvr_gateway_https_exec",  "DVR_gateway/main_https.py"),
    ("dealer_gui_exec",         "dealer_gui/main.py"),
]:
    executables.append(build_component(name, script))


# Run post-build packaging automatically after PyInstaller finishes.
# This makes one build command enough:
# python -m PyInstaller --clean --noconfirm full_build.spec

import subprocess
import sys
from pathlib import Path

_post_build = Path(SPECPATH) / "post_build.py"
if not _post_build.exists():
    raise FileNotFoundError(f"post_build.py not found: {_post_build}")

subprocess.run([sys.executable, str(_post_build)], check=True)