"""
DVR-Gateway  –  FastAPI → downstream DVR socket server
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
from DVR_gateway import app                     # noqa: E402

os.environ["DVR_GATEWAY_MODE"] = "http"          # ✅ inject before importing app
from DVR_gateway import app                      # ✅ will log to dvr_gateway_http.log

# ── settings (fail fast if missing) ────────────────────────────
DVR_BIND_IP   = os.environ["DVR_GATEWAY_BIND_IP"]
DVR_BIND_PORT = int(os.environ["DVR_GATEWAY_HTTP_PORT"])
DVR_TARGET_IP = os.environ["DVR_TARGET_IP"]
DVR_TARGET_PORT = int(os.environ["DVR_TARGET_PORT"])

log = init_logger("dvr_gateway_http").info

def main():
    log(f"[dvr_gateway_http] 🟢 Binding to {DVR_BIND_IP}:{DVR_BIND_PORT}")
    uvicorn.run(
        app.app,
        host=DVR_BIND_IP,
        port=DVR_BIND_PORT,
        log_config=None,
    )

if __name__ == "__main__":
    main()
