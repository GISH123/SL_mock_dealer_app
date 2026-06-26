20260624 Python 3.11.13 Handoff Build Guide

此專案因 20260624 組織與工作安排調整，整理為可交接版本。
本次交接重點是讓接手者可以依照文件完成：

Python 3.11.13 環境建立
requirements 安裝
PyInstaller exe build
本機 smoke test
offline remote computer exe 測試

注意：下方舊的 Python 3.10.12 內容為歷史紀錄。
20260624 之後若要重新 build exe，請優先依照本段 Python 3.11.13 流程。

1. Environment

Recommended build environment:

OS: Windows
Python: 3.11.13
Environment: conda env mock_dealer_py31113
Build tool: PyInstaller
Build spec: full_build.spec

Create environment:

conda create -n mock_dealer_py31113 python=3.11.13 -y
conda activate mock_dealer_py31113
python --version

Expected:

Python 3.11.13
2. Install Dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

This project requires setuptools==81.0.0.

Reason:

PyInstaller or one of its dependencies may import pkg_resources.
Recent setuptools >= 82 no longer provides pkg_resources, which may cause:

ModuleNotFoundError: No module named 'pkg_resources'

If this happens, run:

python -m pip install --force-reinstall "setuptools==81.0.0" wheel
python -c "import setuptools; print(setuptools.__version__)"
python -c "import pkg_resources; print('pkg_resources ok')"

Expected:

81.0.0
pkg_resources ok

Generate locked dependency file:

python -m pip freeze --all | Out-File -Encoding utf8 requirements_py311_locked.txt
3. Test Notes

This project contains integration tests that may require company internal development network services.

Example:

FM / DVR target may point to internal development IP such as 10.146.11.92

Therefore, when building on a local internet-enabled computer outside the company internal network, run_all_tests.py may fail on integration tests.

For this Python 3.11.13 handoff task, the final gate is not run_all_tests.py.

Current validation scope:

1. Python 3.11.13 environment can be created
2. requirements.txt can be installed
3. PyInstaller can build executables successfully
4. generated exe can start on local build machine
5. generated exe can start on offline remote computer

Optional test command:

python run_all_tests.py

Known test limitation:

Some integration tests may fail outside the company internal network.
This does not necessarily mean Python 3.11.13 or exe build failed.
4. Build Executables

Use the existing PyInstaller spec:

python -m PyInstaller --clean --noconfirm full_build.spec

After PyInstaller build completes, run:

python post_build.py

Build output:

dist/
5. Smoke Test

After build, check the generated executables under dist/.

Minimum smoke test:

1. dist folder is generated
2. main GUI exe can start
3. no immediate ImportError
4. no missing config / cert / asset error on startup
5. app can be closed normally
6. copied exe can start on offline remote computer
6. Offline Remote Computer Note

The remote test computer has no internet access.

Do not run these commands on the offline remote computer:

conda create ...
pip install ...

Recommended workflow:

1. Build exe on internet-enabled local computer
2. Copy dist folder and handoff documents to shared network drive
3. Copy release folder from shared network drive to offline remote computer
4. Run exe smoke test on offline remote computer
7. Recommended Handoff Package
mock_dealer_app_py31113_YYYYMMDD/
├─ dist/
├─ README.md
├─ requirements.txt
├─ requirements_py311_locked.txt
├─ full_build.spec
├─ post_build.py
└─ TEST_CHECKLIST.md
==================================================================================================

20250729 龍虎百家 mock dealer  
模擬荷官端: PH龍虎百家  莊閒各一張牌 比數字大小  
用PH 百家的影片  只是只要看位置1   位置2   
跟推論端對測跑幾局  


環境建置流程:  
conda create -n mock_dealer_20250729 python=3.10.12 -y   
conda activate mock_dealer_20250729  
python -m pip install -U pip  
pip install -r requirements.txt  

==================================================================================================

20250623 add pyproject.toml to replace requirement.txt  
pip install --upgrade pip build  
pip install hatch  # OR poetry, whichever you like  
hatch env create   # makes a venv and resolves hashes  

other people to build using my venv : pip install .   


20250418 add local Swagger UI & redoc:  
https://localhost:18080/docs_local will direct to -> https://localhost:18080/static/swagger/index.html   
https://localhost:18080/redoc  => not done at the moment  


20250415 紀錄 : bridge/main.py 使用時，同一個instance不能先http，再轉https，須重開  
嘗試錯誤流程 : 先http mode，嘗試postman打入，成功 ，這時在同一個instance的UI上，先stop，再點https，再start，這時雖然不會報錯，但postman打入過來就會出錯  
需要重新再開一個bridge.py再直接點https開一個https bridge才能成功  

================================================================================================
Mock Dealer Real DVR Test
This test script (test_to_real_DVR.py) performs integration checks by sending HTTP POST commands to a DVR Bridge server.

It simulates a real dealer workflow:

Start recording

Start placing bets

Keepalive pings

Stop placing bets

Stop recording

🌐 HTTP POST API Reference
All HTTP requests are POST requests to:

Endpoint	Purpose	Sample Body  
/record/start	Start recording	{ "table": "T032", "gmcode": "BJ20250411_11240" ,"dvr_ip" : "10.146.11.92"}  
/place/start	Start placing	{ "table": "T032", "gmcode": "BJ20250411_11240" ,"dvr_ip" : "10.146.11.92"}  
/keepalive	Keep connection alive	{ "table": "T032", "gmcode": "BJ20250411_11240" ,"dvr_ip" : "10.146.11.92"}  
/place/stop	Stop placing	{ "table": "T032", "gmcode": "BJ20250411_11240" ,"dvr_ip" : "10.146.11.92"}  
/record/stop	Stop recording	{ "table": "T032", "gmcode": "BJ20250411_11240" ,"dvr_ip" : "10.146.11.92"}  
table: Table ID (e.g., "T032")  


🛠 Manual Testing with curl
You can manually post the same requests with curl like this:

# Start Recording
curl -X POST https://127.0.0.1:18080/record/start -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"  
curl -X 'GET' \
  'https://localhost:18080/record/start?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'  

Example http:  

curl -X POST http://127.0.0.1:18081/record/start -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"  
curl -X 'GET' \
  'http://localhost:18081/record/start?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'  

# Start Placing
curl -X POST https://127.0.0.1:18080/place/start -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"
curl -X 'GET' \
  'https://localhost:18080/place/start?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'

# Keepalive Ping
curl -X POST http://127.0.0.1:18080/keepalive -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"
curl -X 'GET' \
  'https://localhost:18080/keepalive?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'

# Stop Placing
curl -X POST http://127.0.0.1:18080/place/stop -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"
curl -X 'GET' \
  'https://localhost:18080/place/stop?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'  

# Stop Recording
curl -X POST http://127.0.0.1:18080/record/stop -H "Content-Type: application/json" -d "{\"table\": \"T032\", \"gmcode\": \"BJ20250411_11240\", \"dvr_ip\": \"10.146.11.92\"}"  
curl -X 'GET' \
  'https://127.0.0.1:18080/record/stop?gmcode=string&table=T032&dvr_ip=10.146.11.92' \
  -H 'accept: application/json'  


If using HTTPS (https://127.0.0.1:8080), you might need to add -k to ignore SSL certificate issues:  
curl -k -X POST https://127.0.0.1:8080/record/start ...  

# DVR Demo Stack

End‑to‑end playground that mimics a casino **dealer‑client → HTTP bridge →
DVR recorder** workflow.

GUI (Tk) ──TCP──► pydealerclient
│
▼
FastAPI bridge (HTTP/HTTPS) ──TCP──► DVR server (mock or real)


## Components

| Folder | What it is | How to run |
|--------|------------|------------|
| `dealer_gui/` | Mock dealer application with video prediction results | `python -m dealer_gui` |
| `bridge/` | FastAPI service that converts HTTP/HTTPS to the binary DVR socket protocol | `python -m bridge --dvr-ip 10.146.11.92` |
| `mocks/` | `mock_dvr_server.py` – a fake DVR listening on **TCP 11007** | `python -m mocks.mock_dvr_server` |
| `tests/` | Helper launchers<br>• `test_mock2mock.py` starts **all three** above<br>• `test_integration.py` CI script that exercises both HTTP & HTTPS | see script headers |

## Quick demo (all python)

```bash
# 1. start fake DVR
python -m mocks.mock_dvr_server

# 2. start bridge (HTTP)
python -m bridge --dvr-ip 127.0.0.1

# 3. start GUI
python -m dealer_gui









  
  
  
  
  
  
2025/04/10 之前手寫的 README.md  
  
# mock_dealer_app  

command for pyinstaller:
pyinstaller --noconsole dealer.py => before mock_dvr integration
pyinstaller --noconsole main.py

記得要將card_shown_ui複製到exe所在的資料夾 才能顯示卡牌在ui上



# 20250411 run for http/https requests for dvr server

為了要讓測試能測試https,須先進行步驟：

# generates server.key (private) + server.crt (public) valid for 365 days
pip install cryptography
generate_self_signed_cert.py
此為開發環境用的方法，如果在實際生產環境，為了更安全，
需額外設立條件或方式存取server.key跟crt


# tests

test_integration.py :  
只嘗試http request(cmd)至mock_dvr_server, 模擬任何人post至mock_dvr_server應有的規範與測試結果  

test_main.py :  
將mock_dvr_server、dvr_bridge_api、dealer_app.py全都開起來，這時可以開啟pydealerclient做測試，  
20250410測試與debug後，確認可正常接收pydealerclient的detection結果並顯示於dealer_app的UI上  
並且也送出對應的dvr_packets給mock_dvr_server無錯誤  
