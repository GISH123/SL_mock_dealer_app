# tests/test_config.py

import sys
import time
import shutil
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOGS = Path("logs")
CONFIG_FILE = ROOT / "config.env"
BACKUP_FILE = ROOT / "config.env.bak"

TEST_CONFIG = """
MSG_HUB_BIND_IP=127.0.0.91
MSG_HUB_BIND_PORT=9107

FM_GATEWAY_BIND_IP=127.0.0.92
FM_GATEWAY_HTTP_PORT=9207

DVR_GATEWAY_BIND_IP=127.0.0.93
DVR_GATEWAY_HTTP_PORT=9307

FM_TARGET_IP=127.0.0.1
FM_TARGET_PORT=8081

DVR_TARGET_IP=127.0.0.1
DVR_TARGET_PORT=11007

FM_GATEWAY_SERVICE_IP=127.0.0.92
FM_GATEWAY_SERVICE_PORT=9207
DVR_GATEWAY_SERVICE_IP=127.0.0.93
DVR_GATEWAY_SERVICE_PORT=9307
"""

COMPONENTS = {
    "message_hub":      ["python", "message_hub/main.py"],
    "fm_gateway_http":  ["python", "FM_gateway/main_http.py"],
    "dvr_gateway_http": ["python", "DVR_gateway/main_http.py"],
}

EXPECTED_LOG_LINES = {
    "message_hub":     "127.0.0.91:9107",
    "fm_gateway_http": "127.0.0.92:9207",
    "dvr_gateway_http": "127.0.0.93:9307",
}


def test_config_env_usage():
    print("[TEST] Backing up config.env...")
    shutil.copy(CONFIG_FILE, BACKUP_FILE)
    CONFIG_FILE.write_text(TEST_CONFIG)

    processes = []

    try:
        # Clean logs
        LOGS.mkdir(exist_ok=True)
        for file in LOGS.glob("*.log"):
            file.unlink()

        print("[TEST] Starting components...")
        for name, cmd in COMPONENTS.items():
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append((name, proc))
            time.sleep(2)

        # Verify logs
        for name in COMPONENTS.keys():
            log_path = LOGS / f"{name}.log"
            assert log_path.exists(), f"[FAIL] Missing log for {name}: {log_path}"
            content = log_path.read_text(encoding="utf-8")
            expected = EXPECTED_LOG_LINES[name]
            assert expected in content, f"[FAIL] {name} did not bind to expected IP/port: {expected}"
            print(f"[PASS] {name} bound correctly to {expected}")

    finally:
        print("[TEST] Cleaning up...")
        for _, proc in processes:
            proc.terminate()
            proc.wait()

        CONFIG_FILE.write_text(BACKUP_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        BACKUP_FILE.unlink()
        print("[TEST] ✅ test_config.py passed.")

if __name__ == "__main__":
    test_config_env_usage()
