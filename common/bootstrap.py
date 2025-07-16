"""
Common start-up tasks for every entry-point.

✓ Works in dev mode  ➜  python message_hub/main.py
✓ Works in frozen EXE ➜  dist/message_hub.exe
"""

from pathlib import Path
import sys, os
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Project root                                                                #
# --------------------------------------------------------------------------- #
def project_root() -> Path:
    """
    • When running as a PyInstaller bundle  -> EXE directory
    • When running from source             -> repo root (../..)
    """
    if getattr(sys, 'frozen', False):          # PyInstaller sets this
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]  # …/mock_dealer_app

ROOT = project_root()
os.chdir(ROOT)                                 # make cwd predictable
sys.path.insert(0, str(ROOT))                  # import "utils.*" etc.

# --------------------------------------------------------------------------- #
# Environment (.env) and logging                                              #
# --------------------------------------------------------------------------- #
env_file = ROOT / "config.env"
load_dotenv(env_file, override=True)           # silently ignored if missing

# logs/ dir is created by post_build.py, but create defensively in dev mode
log_dir = ROOT / "logs"
log_dir.mkdir(exist_ok=True)

# now initialise the project logger (your existing helper)
from utils.logging_utils import init_logger   # noqa: E402
init_logger(log_dir)                          # expect function (path) -> logger
