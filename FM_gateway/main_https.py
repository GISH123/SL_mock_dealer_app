"""
FM-Gateway – HTTPS Entrypoint
Launches FastAPI app with SSL (used in production).
"""

import uvicorn
# --- PyInstaller bootstrap ------------------------------------
import os, sys
from pathlib import Path
from dotenv import load_dotenv
import argparse  # for --key / --cert

if hasattr(sys, "_MEIPASS"):
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)
# --------------------------------------------------------------

from utils.logging_utils import init_logger       # noqa: E402
from FM_gateway import app                        # noqa: E402

# ── settings (fail fast if missing) ───────────────────────────
FM_BIND_IP    = os.environ["FM_GATEWAY_BIND_IP"]
FM_BIND_PORT  = int(os.environ["FM_GATEWAY_HTTPS_PORT"])
FM_TARGET_IP  = os.environ["FM_TARGET_IP"]
FM_TARGET_PORT = int(os.environ["FM_TARGET_PORT"])

log = init_logger("fm_gateway_https")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", default="server.crt", help="SSL certificate path")
    parser.add_argument("--key",  default="server.key", help="SSL private key path")
    args = parser.parse_args()

    log.info(f"[fm_gateway] 🟢 Binding to {FM_BIND_IP}:{FM_BIND_PORT} (HTTPS)")

    CA_ROOT   = Path(os.getenv("CA_ROOT", "./certs")).expanduser()
    CERT_FILE = os.getenv("CERT_FILE", "server.crt")
    KEY_FILE  = os.getenv("KEY_FILE",  "server.key")
    CERT_PATH = (CA_ROOT / CERT_FILE).resolve()
    KEY_PATH  = (CA_ROOT / KEY_FILE ).resolve()
    
    log.info(f"[dvr_gateway_https] 🟢 CERT_PATH : {CERT_PATH}")
    log.info(f"[dvr_gateway_https] 🟢 KEY_PATH : {KEY_PATH}")

    uvicorn.run(
        app.app,
        host=FM_BIND_IP,
        port=FM_BIND_PORT,
        ssl_keyfile=str(KEY_PATH),
        ssl_certfile=str(CERT_PATH),
        log_config=None,
    )

if __name__ == "__main__":
    main()
