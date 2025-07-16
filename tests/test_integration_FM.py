# tests/test_integration_FM.py

import sys
import time
import socket
import subprocess
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"
MSG_HUB_LOG = LOGS / "message_hub.log"

passed = 0
failed = 0

def build_packet(cmd: int, method_flag: bytes, payload: bytes) -> bytes:
    seq = 1001
    table = b"B001"
    devid = b"obs"
    streamid = b"OBSxS"
    payload_len = len(payload)

    header = struct.pack("!I I I", cmd, 12 + 4 + 4 + 12 + 2 + 1 + payload_len, seq)
    body = struct.pack("!4s 4s 12s H", table, devid, streamid, payload_len)
    return header + body + method_flag + payload

def send_packet(pkt: bytes):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 9007))
    s.sendall(pkt)
    s.close()

def assert_log_contains(label: str, expected_fragment: str):
    global passed, failed
    log_text = MSG_HUB_LOG.read_text(encoding="utf-8")
    if expected_fragment in log_text:
        print(f"[PASS] ✅ {label}")
        passed += 1
    else:
        print(f"[FAIL] ❌ {label}")
        failed += 1

def test_fm_forwarding():
    processes = []
    try:
        print("[TEST] Launching mock_FM...")
        p1 = subprocess.Popen(["python", "mock_FM/main.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append(p1)
        time.sleep(1)

        print("[TEST] Launching fm_gateway and message_hub...")
        p2 = subprocess.Popen(["python", "FM_gateway/main_http.py"])
        p3 = subprocess.Popen(["python", "message_hub/main.py"])
        processes.extend([p2, p3])
        time.sleep(2)

        # 1. GET /forward_inputjson
        print("[TEST] Sending → GET /forward_inputjson")
        pkt = build_packet(0x32001, b"\x00", b"{header:json,body:[card_index:1,3,4,5,6],sceneName:Near}")
        send_packet(pkt)
        time.sleep(1)
        assert_log_contains("GET /forward_inputjson", "/forward_inputjson")

        # 2. POST /forward_inputjson
        print("[TEST] Sending → POST /forward_inputjson")
        pkt = build_packet(0x32001, b"\x01", b"{header:json,body:[card_index:7,8,9],sceneName:Far}")
        send_packet(pkt)
        time.sleep(1)
        assert_log_contains("POST /forward_inputjson", "/forward_inputjson")

        # 3. GET /forward_scene_switch
        print("[TEST] Sending → GET /forward_scene_switch")
        pkt = build_packet(0x31001, b"\x00", b"Near")
        send_packet(pkt)
        time.sleep(1)
        assert_log_contains("GET /forward_scene_switch", "/forward_scene_switch")

        # 4. POST /forward_scene_switch
        print("[TEST] Sending → POST /forward_scene_switch")
        pkt = build_packet(0x31001, b"\x01", b"Far")
        send_packet(pkt)
        time.sleep(1)
        assert_log_contains("POST /forward_scene_switch", "/forward_scene_switch")

    finally:
        print("[TEST] Cleaning up...")
        for p in processes:
            p.terminate()
            p.wait()

        # 🧾 Final summary
        print("\n[SUMMARY]")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print("[TEST] test_integration_FM.py done.")

if __name__ == "__main__":
    test_fm_forwarding()
