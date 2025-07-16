"""
FM-Gateway  –  FastAPI → downstream FM server
"""

import uvicorn
# --- PyInstaller bootstrap ------------------------------------
import os, sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys, "_MEIPASS"):
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)
# --------------------------------------------------------------

from utils.logging_utils import init_logger     # noqa: E402
from FM_gateway import app                      # noqa: E402

# ── settings (fail fast if missing) ────────────────────────────
FM_BIND_IP   = os.environ["FM_GATEWAY_BIND_IP"]
FM_BIND_PORT = int(os.environ["FM_GATEWAY_HTTP_PORT"])
FM_TARGET_IP = os.environ["FM_TARGET_IP"]
FM_TARGET_PORT = int(os.environ["FM_TARGET_PORT"])

log = init_logger("fm_gateway_http")

def main():
    log.info(f"[fm_gateway] 🟢 Binding to {FM_BIND_IP}:{FM_BIND_PORT}")
    uvicorn.run(
        app.app,
        host=FM_BIND_IP,
        port=FM_BIND_PORT,
        log_config=None,
    )

if __name__ == "__main__":
    main()
