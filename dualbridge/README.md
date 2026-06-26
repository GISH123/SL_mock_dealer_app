# DualBridge (TCP <-> WebSocket)

This service bridges:
- **TCP** (ImageDetector side) <-> **WebSocket** (Mock Dealer side)

## Ports / .env
Edit `.env` next to `dualbrige.py` or next to the packaged `dualbrige.exe`:

- `DUALBRIDGE_TCP_PORT` (default `2331`)
- `DUALBRIDGE_WS_PORT` (default `3331`)

## Run (python)
```bash
pip install websockets python-dotenv
python dualbrige.py
```

## Package (PyInstaller)
```bash
pip install pyinstaller websockets python-dotenv
pyinstaller -y dualbrige.spec
```

The build is **onedir** and keeps `.env` next to the exe so you can edit ports without rebuilding.
