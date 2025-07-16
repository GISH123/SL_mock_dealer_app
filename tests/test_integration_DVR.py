# tests/test_integration_DVR.py

import sys
import time
import struct
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"
MSG_HUB_LOG = LOGS / f"message_hub.log"
DVR_GATEWAY_LOG = LOGS / f"dvr_gateway_http.log"
MOCK_DVR_LOG = ROOT / "mock_dvr_server.log"  # we'll redirect it ourselves

def build_dvr_packet() -> bytes:
    cmd     = 0x20001  # START_RECORD
    size    = 30
    ver     = 1
    table   = b"B001"
    gmcode  = b"ROUND01"

    return struct.pack("!I I H 4s 16s", cmd, size, ver, table.ljust(4, b"\0"), gmcode.ljust(16, b"\0"))


def test_dvr_forwarding():
    processes = []

    try:
        print("[TEST] Launching mock_dvr_server...")
        mock_dvr = subprocess.Popen(
            ["python", "mock_dvr_server/mock_dvr_server.py"],
            stdout=open(MOCK_DVR_LOG, "w"),
            stderr=subprocess.STDOUT
        )
        processes.append(mock_dvr)
        time.sleep(1)

        print("[TEST] Launching dvr_gateway and message_hub...")
        dvr_proc = subprocess.Popen(["python", "DVR_gateway/main_http.py"])
        hub_proc = subprocess.Popen(["python", "message_hub/main.py"])
        processes.extend([dvr_proc, hub_proc])
        time.sleep(2)

        # Send binary DVR packet to message hub
        print("[TEST] Sending DVR packet to message_hub (127.0.0.1:9007)...")
        pkt = build_dvr_packet()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 9007))
        s.sendall(pkt)
        s.close()
        time.sleep(2)

        # Read and validate DVR forwarding logs
        log_text = MSG_HUB_LOG.read_text(encoding="utf-8")
        assert "[Hub→DVR] Posting to DVR Gateway" in log_text, "[FAIL] DVR post missing in hub log"

        dvr_text = DVR_GATEWAY_LOG.read_text(encoding="utf-8")
        assert "cmd=0x20001" in dvr_text, "[FAIL] DVR command not sent to DVR server"
        assert "← raw" in dvr_text, "[FAIL] No DVR response received"

        mock_text = MOCK_DVR_LOG.read_text(encoding="utf-8")
        assert "START_RECORD" in mock_text, "[FAIL] mock_dvr_server did not parse DVR packet"

        print("[PASS] DVR forward verified via all logs")

    finally:
        print("[TEST] Cleaning up...")
        for p in processes:
            p.terminate()
            p.wait()
        print("[TEST] ✅ test_integration_DVR.py passed.")

if __name__ == "__main__":
    test_dvr_forwarding()
