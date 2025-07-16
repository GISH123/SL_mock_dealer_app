
import subprocess
import time
import threading
import os
import sys

def run_process(name, command, cwd=None):
    def target():
        print(f"[TEST] Starting: {name}")
        process = subprocess.Popen(
            [sys.executable, "-u"] + command[1:],  # unbuffered mode
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",    # ✅ FIX
            errors="replace"     # ✅ prevent UnicodeDecodeError
        )
        for line in iter(process.stdout.readline, ''):
            print(f"[{name}] {line}", end='')
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    message_hub_cmd = [sys.executable, "message_hub/main.py"]
    fm_gateway_cmd = [sys.executable, "-m", "FM_gateway.main_http"]
    dvr_gateway_cmd = [sys.executable, "-m", "DVR_gateway.main_http"]
    dealer_gui_cmd = [sys.executable, "-m", "dealer_gui.main"]

    threads = []
    threads.append(run_process("message_hub", message_hub_cmd, cwd=PROJECT_ROOT))
    threads.append(run_process("fm_gateway", fm_gateway_cmd, cwd=PROJECT_ROOT))
    threads.append(run_process("dvr_gateway", dvr_gateway_cmd, cwd=PROJECT_ROOT))

    time.sleep(2)
    threads.append(run_process("dealer_gui", dealer_gui_cmd, cwd=PROJECT_ROOT))

    print("[TEST] All components launched. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[TEST] Exiting test runner.")
