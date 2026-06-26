# SL Mock Dealer App

## Final Repository Status

This repository has been finalized as a Python 3.11.13 handoff repository.

The final layout intentionally separates two responsibilities:

1. **Gateway / bridge build flow** stays at the repository root.
2. **Mock dealer and game applications** are grouped under `mock_dealer_games/`.

This keeps the original full-build gateway package usable while making the mock dealer tools easier to find, preserve, and import later.

---

## Final Repository Layout

```text
SL_mock_dealer_app/
├─ DVR_gateway/
├─ FM_gateway/
├─ common/
├─ dualbridge/
├─ message_hub/
├─ static/
├─ utils/
├─ mock_dealer_games/
├─ full_build.spec
├─ post_build.py
├─ start_all_windows.bat
├─ start_all_linux.sh
├─ requirements.txt
├─ requirements_py311_locked.txt
└─ README.md
```

### Gateway / full-build files kept at root

The following files and folders are intentionally kept at the repository root because they are part of the gateway and full-build workflow:

```text
DVR_gateway/
FM_gateway/
common/
dualbridge/
message_hub/
static/
utils/
full_build.spec
post_build.py
start_all_windows.bat
start_all_linux.sh
requirements.txt
requirements_py311_locked.txt
```

The current gateway package should still be built from the repository root with:

```powershell
python -m PyInstaller --clean --noconfirm full_build.spec
```

`post_build.py` belongs to the root-level gateway/full-build workflow. In the current handoff version, `full_build.spec` is expected to run `post_build.py` as part of the one-command build flow. If needed, `post_build.py` can still be run manually as a fallback check after PyInstaller.

### Mock dealer games

All mock dealer and game-related tools are now grouped under:

```text
mock_dealer_games/
```

Current contents:

```text
mock_dealer_games/
├─ dealer_BAC/
├─ dealer_ball3/
├─ dealer_dragontiger/
├─ dealer_dragontiger_ws/
├─ dealer_gui/
├─ mock_FM/
├─ mock_dvr_server/
├─ card_shown_ui/
├─ static/
├─ shared_build_utils.py
├─ shared_runtime.py
├─ requirements.txt
├─ version.txt
└─ versionhttp.txt
```

Purpose of the main folders:

| Path | Purpose |
|---|---|
| `mock_dealer_games/dealer_BAC/` | Final BAC mock dealer source imported from the remote final project |
| `mock_dealer_games/dealer_ball3/` | Final BALL3 mock dealer source, merged with the old main branch's BALL3 assets and metadata |
| `mock_dealer_games/dealer_dragontiger/` | Original DragonTiger mock dealer source from main |
| `mock_dealer_games/dealer_dragontiger_ws/` | Original DragonTiger WebSocket mock dealer source from main |
| `mock_dealer_games/dealer_gui/` | Original generic dealer GUI source from main |
| `mock_dealer_games/mock_FM/` | Original FM mock source from main |
| `mock_dealer_games/mock_dvr_server/` | Original mock DVR server source from main |
| `mock_dealer_games/card_shown_ui/` | Shared card UI image assets |
| `mock_dealer_games/static/` | Swagger/Redoc static assets for mock dealer-related tools |
| `mock_dealer_games/shared_build_utils.py` | Shared build helper imported from the final remote project |
| `mock_dealer_games/shared_runtime.py` | Shared runtime helper imported from the final remote project |

### Final cleanup summary

The following cleanup was completed before this README update:

- Gateway build flow was preserved at repository root.
- `mock_dealer_final_app/` was renamed and reorganized into `mock_dealer_games/`.
- Final remote `dealer_BAC` source was preserved under `mock_dealer_games/dealer_BAC/`.
- Final remote `dealer_ball3` source was preserved under `mock_dealer_games/dealer_ball3/`.
- Existing main-branch mock dealer folders were moved into `mock_dealer_games/` instead of staying scattered at repository root.
- Runtime/config/build artifacts were kept out of Git.

### Important repository hygiene rule

Do not commit local runtime/config/build artifacts, including:

```text
.env
*.env
config.env
config_*.env
server.key
server.crt
*.key
*.crt
*.pem
*.p12
*.pfx
*.bundle
*.zip
*.7z
*.exe
*.dll
*.so
*.pyd
dist/
build/
logs/
*.log
__pycache__/
```

Bundle files are transfer artifacts only. They should not be committed.

---

## 20260624 Python 3.11.13 Handoff Build Guide

此專案因 20260624 組織與工作安排調整，整理為可交接版本。

本次交接重點是讓接手者可以依照文件完成：

1. Python 3.11.13 環境建立
2. `requirements.txt` 安裝
3. PyInstaller exe build
4. 本機 smoke test
5. offline remote computer exe 測試

> 注意：下方舊的 Python 3.10.12 / 2025 開發紀錄為歷史紀錄。  
> 20260624 之後若要重新 build exe，請優先依照本段 Python 3.11.13 流程。

---

## 1. Environment

Recommended build environment:

| Item | Value |
|---|---|
| OS | Windows |
| Python | 3.11.13 |
| Conda env | `mock_dealer_py31113` |
| Build tool | PyInstaller |
| Build spec | `full_build.spec` |

Create environment:

```powershell
conda create -n mock_dealer_py31113 python=3.11.13 -y
conda activate mock_dealer_py31113
python --version
```

Expected:

```text
Python 3.11.13
```

---

## 2. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This project requires:

```text
setuptools==81.0.0
```

Reason:

PyInstaller or one of its dependencies may import `pkg_resources`. Recent `setuptools >= 82` no longer provides `pkg_resources`, which may cause:

```text
ModuleNotFoundError: No module named 'pkg_resources'
```

If this happens, run:

```powershell
python -m pip install --force-reinstall "setuptools==81.0.0" wheel
python -c "import setuptools; print(setuptools.__version__)"
python -c "import pkg_resources; print('pkg_resources ok')"
```

Expected:

```text
81.0.0
pkg_resources ok
```

Generate locked dependency file:

```powershell
python -m pip freeze --all | Out-File -Encoding utf8 requirements_py311_locked.txt
```

---

## 3. Test Notes

This project contains integration tests that may require company internal development network services.

Example:

```text
FM / DVR target may point to an internal development IP.
```

Therefore, when building on a local internet-enabled computer outside the company internal network, `run_all_tests.py` may fail on integration tests.

For this Python 3.11.13 handoff task, the final gate is **not** `run_all_tests.py`.

Current validation scope:

1. Python 3.11.13 environment can be created.
2. `requirements.txt` can be installed.
3. PyInstaller can build executables successfully.
4. Generated exe can start on local build machine.
5. Generated exe can start on offline remote computer.

Optional test command:

```powershell
python run_all_tests.py
```

Known test limitation:

```text
Some integration tests may fail outside the company internal network.
This does not necessarily mean Python 3.11.13 or exe build failed.
```

---

## 4. Build Executables

Use the existing PyInstaller spec from the repository root:

```powershell
python -m PyInstaller --clean --noconfirm full_build.spec
```

In the current handoff version, `full_build.spec` is expected to run `post_build.py` automatically after PyInstaller completes, producing a complete release-style `dist/` package.

If you need to verify or rerun the packaging step manually, run:

```powershell
python post_build.py
```

Build output:

```text
dist/
```

---

## 5. Smoke Test

After build, check the generated executables under `dist/`.

Minimum smoke test:

1. `dist/` folder is generated.
2. Main GUI exe can start.
3. No immediate `ImportError`.
4. No missing config / cert / asset error on startup.
5. App can be closed normally.
6. Copied exe can start on offline remote computer.

Example:

```powershell
dist\dealer_gui_exec\dealer_gui_exec.exe
```

---

## 6. Offline Remote Computer Note

The remote test computer has no internet access.

Do **not** run these commands on the offline remote computer:

```powershell
conda create ...
pip install ...
```

Recommended workflow:

1. Build exe on an internet-enabled local computer.
2. Prepare release folder.
3. Compress the release folder into a single `.7z` archive.
4. Copy the `.7z` archive to the shared network drive.
5. Copy the `.7z` archive from the shared network drive to the offline remote computer local disk.
6. Extract on the offline remote computer local disk.
7. Run exe smoke test from the offline remote computer local disk.

Do not run exe directly from the shared network drive.

---

## 7. Recommended Handoff Package

```text
mock_dealer_app_py31113_YYYYMMDD/
├─ dist/
├─ README.md
├─ requirements.txt
├─ requirements_py311_locked.txt
├─ full_build.spec
├─ post_build.py
├─ mock_dealer_games/
└─ TEST_CHECKLIST.md
```

`mock_dealer_games/` is included in the source repository as the consolidated location for mock dealer and game tools. Build outputs should still be distributed separately through the release package, not committed into Git.

---

## 8. Repository Hygiene

The repository should keep source code and handoff documents only.

Do not commit:

```text
dist/
build/
dist_VM_linux/dist/
*.exe
*.dll
*.so
*.pyd
*.zip
*.7z
.env
*.env
config.env
config_*.env
*.key
*.crt
*.pem
*.p12
*.pfx
logs/
*.log
```

Build outputs and sanitized exe packages should be transferred separately as release artifacts, not committed into the source tree.

---

# Historical Notes

The following sections are older development notes. They are kept for context only.

---

## 20250729 龍虎百家 Mock Dealer

模擬荷官端：PH 龍虎百家，莊閒各一張牌，比數字大小。

使用 PH 百家的影片，只看位置 1、位置 2，並與推論端對測跑幾局。

Historical environment setup:

```powershell
conda create -n mock_dealer_20250729 python=3.10.12 -y
conda activate mock_dealer_20250729
python -m pip install -U pip
pip install -r requirements.txt
```

---

## 20250623 pyproject.toml Note

Added `pyproject.toml` to replace / improve the old `requirements.txt` workflow.

```powershell
pip install --upgrade pip build
pip install hatch
hatch env create
```

For other people to build using the package:

```powershell
pip install .
```

---

## 20250418 Local Swagger UI and Redoc

Local Swagger UI:

```text
https://localhost:18080/docs_local
```

Redirects to:

```text
https://localhost:18080/static/swagger/index.html
```

Redoc note:

```text
https://localhost:18080/redoc
```

At the time of writing, Redoc was not fully completed.

---

## 20250415 Bridge Instance Note

`bridge/main.py` 使用時，同一個 instance 不能先 HTTP，再轉 HTTPS，須重開。

Observed issue:

1. Start HTTP mode.
2. Send Postman request successfully.
3. In the same UI instance, click Stop.
4. Switch to HTTPS.
5. Click Start.
6. No immediate error is shown, but incoming Postman requests fail.

Required workaround:

```text
Restart bridge.py and directly start HTTPS bridge mode.
```

---

# Mock Dealer Real DVR Test

This test script, `test_to_real_DVR.py`, performs integration checks by sending HTTP POST commands to a DVR Bridge server.

It simulates a real dealer workflow:

1. Start recording.
2. Start placing bets.
3. Keepalive pings.
4. Stop placing bets.
5. Stop recording.

---

## HTTP POST API Reference

All HTTP requests are POST requests.

Use the actual internal DVR IP only inside the company internal test environment.

| Endpoint | Purpose | Sample Body |
|---|---|---|
| `/record/start` | Start recording | `{ "table": "T032", "gmcode": "BJ20250411_11240", "dvr_ip": "<DVR_IP>" }` |
| `/place/start` | Start placing | `{ "table": "T032", "gmcode": "BJ20250411_11240", "dvr_ip": "<DVR_IP>" }` |
| `/keepalive` | Keep connection alive | `{ "table": "T032", "gmcode": "BJ20250411_11240", "dvr_ip": "<DVR_IP>" }` |
| `/place/stop` | Stop placing | `{ "table": "T032", "gmcode": "BJ20250411_11240", "dvr_ip": "<DVR_IP>" }` |
| `/record/stop` | Stop recording | `{ "table": "T032", "gmcode": "BJ20250411_11240", "dvr_ip": "<DVR_IP>" }` |

`table`: Table ID, for example `T032`.

---

## Manual Testing with curl

Replace `<DVR_IP>` with the actual DVR IP inside the internal development network.

### Start Recording

HTTPS POST:

```bash
curl -X POST https://127.0.0.1:18080/record/start \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"
```

HTTPS GET:

```bash
curl -X GET "https://localhost:18080/record/start?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

HTTP POST:

```bash
curl -X POST http://127.0.0.1:18081/record/start \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"
```

HTTP GET:

```bash
curl -X GET "http://localhost:18081/record/start?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

### Start Placing

```bash
curl -X POST https://127.0.0.1:18080/place/start \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"

curl -X GET "https://localhost:18080/place/start?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

### Keepalive Ping

```bash
curl -X POST http://127.0.0.1:18080/keepalive \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"

curl -X GET "https://localhost:18080/keepalive?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

### Stop Placing

```bash
curl -X POST http://127.0.0.1:18080/place/stop \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"

curl -X GET "https://localhost:18080/place/stop?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

### Stop Recording

```bash
curl -X POST http://127.0.0.1:18080/record/stop \
  -H "Content-Type: application/json" \
  -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"<DVR_IP>\"}"

curl -X GET "https://127.0.0.1:18080/record/stop?gmcode=string&table=T032&dvr_ip=<DVR_IP>" \
  -H "accept: application/json"
```

If using HTTPS with a self-signed certificate, add `-k` to ignore SSL certificate issues:

```bash
curl -k -X POST https://127.0.0.1:8080/record/start ...
```

---

# DVR Demo Stack

End-to-end playground that mimics a casino dealer-client to HTTP bridge to DVR recorder workflow.

```text
GUI (Tk)
  │
  ├─ TCP ──► pydealerclient
  │
  ▼
FastAPI bridge (HTTP/HTTPS)
  │
  └─ TCP ──► DVR server, mock or real
```

---

## Components

| Folder | What it is | How to run |
|---|---|---|
| `dealer_gui/` | Mock dealer application with video prediction results | `python -m dealer_gui` |
| `bridge/` | FastAPI service that converts HTTP/HTTPS to the binary DVR socket protocol | `python -m bridge --dvr-ip <DVR_IP>` |
| `mocks/` | `mock_dvr_server.py`, a fake DVR listening on TCP 11007 | `python -m mocks.mock_dvr_server` |
| `tests/` | Helper launchers and integration scripts | See script headers |

---

## Quick Demo

```bash
# 1. Start fake DVR
python -m mocks.mock_dvr_server

# 2. Start bridge over HTTP
python -m bridge --dvr-ip 127.0.0.1

# 3. Start GUI
python -m dealer_gui
```

---

# 2025/04/10 Older Manual README Notes

## mock_dealer_app

Historical PyInstaller commands:

```powershell
pyinstaller --noconsole dealer.py
pyinstaller --noconsole main.py
```

Remember to copy `card_shown_ui` to the exe folder so the UI can show card images.

---

## 20250411 HTTP / HTTPS DVR Server Requests

To test HTTPS, generate a self-signed certificate first.

This generates `server.key` and `server.crt`, valid for 365 days:

```powershell
pip install cryptography
python generate_self_signed_cert.py
```

This method is for development environment only. In production, a more secure way should be used to manage access to `server.key` and `server.crt`.

---

## Tests

### `test_integration.py`

Attempts HTTP requests from CMD to `mock_dvr_server`.

Purpose:

```text
Simulate expected request format and test result for requests sent to mock_dvr_server.
```

### `test_main.py`

Starts:

1. `mock_dvr_server`
2. `dvr_bridge_api`
3. `dealer_app.py`

Then open `pydealerclient` for testing.

Historical result from 20250410:

```text
Confirmed that the app can correctly receive detection results from pydealerclient,
display them on dealer_app UI, and send corresponding DVR packets to mock_dvr_server.
```
