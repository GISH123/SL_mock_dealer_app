# --- PyInstaller bootstrap ------------------------------------
import os, sys
from pathlib import Path
from dotenv import load_dotenv
import argparse  # for --key/--cert

if hasattr(sys, "_MEIPASS"):
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)
# --------------------------------------------------------------
import argparse                     # ✅ Needed for --key/--cert
from utils.logging_utils import init_logger     # ✅ new

os.environ["DVR_GATEWAY_MODE"] = "https"         # ✅ this determines log file name
from DVR_gateway import app as dvr_app           # ✅ logs to dvr_gateway_https.log
# --------------------------------------------------------------
import uvicorn
# ── Strict env ────────────────────────────────────────────────
DVR_GATEWAY_BIND_IP    = os.environ["DVR_GATEWAY_BIND_IP"]
DVR_GATEWAY_HTTPS_PORT = int(os.environ["DVR_GATEWAY_HTTPS_PORT"])

DVR_TARGET_IP   = os.environ["DVR_TARGET_IP"]
DVR_TARGET_PORT = int(os.environ["DVR_TARGET_PORT"])

log = init_logger("dvr_gateway_https")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--key",  default="server.key")
    p.add_argument("--cert", default="server.crt")
    args = p.parse_args()

    log.info(f"[dvr_gateway_https] 🟢 Binding to {DVR_GATEWAY_BIND_IP}:{DVR_GATEWAY_HTTPS_PORT}")

    CA_ROOT   = Path(os.getenv("CA_ROOT", "./certs")).expanduser()
    CERT_FILE = os.getenv("CERT_FILE", "server.crt")
    KEY_FILE  = os.getenv("KEY_FILE",  "server.key")
    CERT_PATH = (CA_ROOT / CERT_FILE).resolve()
    KEY_PATH  = (CA_ROOT / KEY_FILE ).resolve()

    log.info(f"[dvr_gateway_https] 🟢 CERT_PATH : {CERT_PATH}")
    log.info(f"[dvr_gateway_https] 🟢 KEY_PATH : {KEY_PATH}")

    uvicorn.run(
        dvr_app.app,
        host=DVR_GATEWAY_BIND_IP,
        port=DVR_GATEWAY_HTTPS_PORT,
        ssl_keyfile=str(KEY_PATH),
        ssl_certfile=str(CERT_PATH),
        log_config=None,
    )

if __name__ == "__main__":
    main()
