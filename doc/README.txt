20250623 update:

pyinstaller full_build.spec -y --clean
python post_build.py

確認config.env與server.crt和server.key在dist/底下(windows需手動放置，linux則會在generate_ssl.sh製造)
example usage:
cd dist/
./dvr_gateway_http_exec/dvr_gateway_http_exec.exe 


===========================================================================

[ dealer_gui ]
      │
      ▼  (Socket)
[ message_hub ] ──────► [ fm_gateway ] ────► [ FieldManager ]
      │
      └───────────────► [ dvr_gateway ] ───► [ DVR ]


file structure:

mock_dealer_app/
├── dealer_gui/              ← GUI for mock dealer
├── fm_gateway/              ← FastAPI to FM
├── dvr_gateway/             ← FastAPI to DVR socket
├── message_hub/             ← New TCP → HTTP dispatcher
├── common/                  ← protocol constants / helpers

