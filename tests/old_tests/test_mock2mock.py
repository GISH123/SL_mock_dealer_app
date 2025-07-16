"""
Launch mock DVR ➜ bridge ➜ dealer GUI (manual demo).
Safe for PyInstaller – spawns `python -m module` instead of script paths.
"""

import subprocess, sys, time, signal, shutil, threading, itertools, importlib.util, runpy, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PY   = shutil.which("python") or sys.executable

def spawn(tag, module, *args):
    cmd = [PY, "-m", module, *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="ignore",   # ✅ important: ignore invalid bytes
                         bufsize=1, env=env)
    threading.Thread(
        target=lambda: [print(f"[{tag}] {l.rstrip()}") for l in iter(p.stdout.readline, '')],
        daemon=True,
    ).start()
    return p

def main():
    procs={}
    try:
        procs["dvr"]=spawn("DVR","mocks.mock_dvr_server"); time.sleep(1)
        procs["br" ]=spawn("BR","bridge","--mode","http"); time.sleep(1)
        procs["gui"]=spawn("GUI","dealer_gui");            procs["gui"].wait()
    finally:
        for p in procs.values():
            if p.poll() is None: p.send_signal(signal.SIGTERM)
        time.sleep(1)
        for p in procs.values():
            if p.poll() is None: p.kill()

if __name__=="__main__": main()
