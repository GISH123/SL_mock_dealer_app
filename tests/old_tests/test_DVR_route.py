import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
ROOT = Path(__file__).resolve().parents[1]

modules = [
    "DVR_gateway.main_http",         # ✅ corrected from 'bridge.main_http'
    "message_hub.main",
    "mock_dvr_server.mock_dvr_server",
    "dealer_gui.main",
]

def main():
    processes = []
    for mod in modules:
        print(f"[Test] Launching: {mod}")
        p = subprocess.Popen([PYTHON, "-m", mod], cwd=ROOT)
        processes.append(p)

    print("\n[Test] ✅ All modules running.")
    print("[Test] Interact with DVR buttons in dealer_gui window.")
    print("[Test] Logs from DVR_gateway, message_hub, and mock_dvr_server should appear below.\n")
    try:
        input("[Test] Press ENTER to terminate everything...\n")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("[Test] ✅ All terminated.")

if __name__ == "__main__":
    main()
