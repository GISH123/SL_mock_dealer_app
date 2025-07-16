# tests/test_log_creation.py

import subprocess
import time
from pathlib import Path

COMPONENTS = {
    "message_hub":       ["python", "message_hub/main.py"],
    "fm_gateway_http":   ["python", "FM_gateway/main_http.py"],
    "dvr_gateway_http":  ["python", "DVR_gateway/main_http.py"],
}

def launch_and_verify_logs():
    today = time.strftime("%Y-%m-%d")
    processes = []

    print("[TEST] Launching components...")

    for name, cmd in COMPONENTS.items():
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append((name, proc))
        time.sleep(2)

    print("[TEST] Verifying log files...")

    for name, proc in processes:
        base_log = Path(f"logs/{name}.log")
        rotated_log = Path(f"logs/{name}.log.{today}")

        assert base_log.exists() or rotated_log.exists(), \
            f"[FAIL] Log not found: logs/{name}.log or .log.{today}"

        found_log = base_log if base_log.exists() else rotated_log
        content = found_log.read_text(encoding="utf-8")
        assert "Binding to" in content, f"[FAIL] 'Binding to' not found in {found_log}"
        print(f"[PASS] '{name}' log contains bind info: {found_log.name}")

    print("[TEST] Cleaning up processes...")
    for _, proc in processes:
        proc.terminate()
        proc.wait()

    print("[TEST] ✅ test_log_creation passed.")

if __name__ == "__main__":
    launch_and_verify_logs()
