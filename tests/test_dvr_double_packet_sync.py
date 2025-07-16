# test_dvr_double_packet_sync.py

import socket
import struct
from datetime import datetime

# DVR config
DVR_IP = "10.146.11.92"
# DVR_IP = "127.0.0.1"
DVR_PORT = 11007

# DVR packet constants
CMD_START_RECORD = 0x20001
VERSION = 1
PACKET_SIZE = 30

TABLE = "T032"
GMCODE = "ROUND01"

def build_single_packet():
    table = TABLE.encode().ljust(4, b"\0")
    gmcode = GMCODE.encode().ljust(16, b"\0")
    pkt = struct.pack("!I I H 4s 16s", CMD_START_RECORD, PACKET_SIZE, VERSION, table, gmcode)
    return pkt

def send_double_packet():
    pkt1 = build_single_packet()
    pkt2 = build_single_packet()
    double_packet = pkt1 + pkt2  # Total length = 60 bytes

    print(f"[{datetime.now()}] → Connecting to {DVR_IP}:{DVR_PORT}")
    print(f"[DEBUG] Sending 2x packet (hex): {double_packet.hex()}")

    with socket.create_connection((DVR_IP, DVR_PORT), timeout=5) as sock:
        sock.sendall(double_packet)

        try:
            response = sock.recv(PACKET_SIZE)
            print(f"[{datetime.now()}] ← Received response (hex): {response.hex()}")
        except socket.timeout:
            print("[ERROR] Timed out waiting for response")
        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    send_double_packet()
