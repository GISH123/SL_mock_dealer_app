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
        "route": "inputjson",
        "devId": "obs",
        "streamId": "test_make_cypher",
        "tableId": "B002",
        "inputName": "{header:json,body:[card:1,3,4],sceneName:Near}"
    }
    print(make_cipher(body))
