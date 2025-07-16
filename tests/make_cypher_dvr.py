    # ─── make_cipher.py ───────────────────────────────────────────
import os, json, base64, secrets, string

SCRAMBLE_KEY = os.getenv("SCRAMBLE_KEY", "HWm9q2StMUErv34a").encode()

def xor(data: bytes) -> bytes:
    key = SCRAMBLE_KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def make_cipher(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(xor(raw)).decode()

if __name__ == "__main__":
    body = {
        "route": "record",
        "action": "start",
        "gmcode": "make_cypher_test",
        "table":  "T032",
        "dvr_ip": "127.0.0.1",
        "dvr_port": 11007
    }
    print(make_cipher(body))