import subprocess
import time
import sys
import os
from pathlib import Path

# Define project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_module(name):
    return subprocess.Popen([sys.executable, "-m", name], cwd=PROJECT_ROOT)

def main():
    print("[Test] Starting full FM route chain...")

    # Start services
    msg_hub_proc = run_module("message_hub.main")
    fm_gateway_proc = run_module("FM_gateway.main_http")
    mock_fm_proc = run_module("mock_FM.main")
    dealer_gui_proc = run_module("dealer_gui.main")

    try:
        print("[Test] All modules started. Waiting for logs...")

        # Allow time for startup and GUI user input
        time.sleep(60)

        print("[Test] Test complete. Please verify logs manually.")
        input("[Press Enter to terminate all processes]")

    finally:
        for proc in [dealer_gui_proc, mock_fm_proc, fm_gateway_proc, msg_hub_proc]:
            if proc.poll() is None:
                print(f"[Test] Terminating {proc.args[2]}")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

if __name__ == "__main__":
    main()
