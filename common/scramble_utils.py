import os, base64, json

_KEY = os.environ["SCRAMBLE_KEY"].encode()  # e.g. 'Z3G8' (any length)

def _xor(data: bytes) -> bytes:
    key = _KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def encode_payload(obj: dict) -> str:
    raw = json.dumps(obj).encode()
    scrambled = _xor(raw)
    return base64.urlsafe_b64encode(scrambled).decode()

def decode_payload(b64: str) -> dict:
    scrambled = base64.urlsafe_b64decode(b64)
    raw = _xor(scrambled)
    return json.loads(raw)
