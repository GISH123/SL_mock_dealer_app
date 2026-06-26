@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM start_all_windows.bat
REM Windows launcher for mock_dealer_app PyInstaller dist package.
REM Put this file inside the dist/ folder, next to config.env and static/.
REM ============================================================

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

echo.
echo [INFO] Base directory: %BASE_DIR%
echo [INFO] Starting mock dealer app gateway services for Windows...
echo.

REM ---- Basic handoff package checks ----
if not exist "config.env" (
    echo [WARN] config.env not found in %BASE_DIR%
    echo        Some gateway services may fail if they require config.env from dist root.
    echo.
)

if not exist "static\swagger\index.html" (
    echo [WARN] static\swagger\index.html not found.
    echo        Swagger UI local assets may not load.
    echo.
)

REM ---- HTTPS certificate note ----
REM Linux start_all_linux.sh calls generate_ssl.sh.
REM Native Windows usually cannot run .sh unless Git Bash/MSYS is installed.
REM If HTTPS gateways fail with missing cert/key errors, generate/copy server.crt and server.key manually.
if not exist "server.crt" (
    echo [WARN] server.crt not found in dist root.
    echo        HTTPS gateway may still work if cert path is configured elsewhere.
)
if not exist "server.key" (
    echo [WARN] server.key not found in dist root.
    echo        HTTPS gateway may still work if key path is configured elsewhere.
)
echo.

call :start_service "dvr_http"      "dvr_gateway_http_exec\dvr_gateway_http_exec.exe"
call :start_service "dvr_https"     "dvr_gateway_https_exec\dvr_gateway_https_exec.exe"
call :start_service "fm_http"       "fm_gateway_exec\fm_gateway_exec.exe"
call :start_service "fm_https"      "fm_gateway_https_exec\fm_gateway_https_exec.exe"
call :start_service "message_hub"   "message_hub_exec\message_hub_exec.exe"

if /I "%~1"=="--with-gui" (
    call :start_service "dealer_gui" "dealer_gui_exec\dealer_gui_exec.exe"
) else (
    echo [INFO] dealer_gui_exec was not started by default.
    echo        To start it too, run:
    echo        start_all_windows.bat --with-gui
    echo.
)

echo [INFO] Startup commands have been issued.
echo [INFO] Check the opened service windows for ImportError, missing config, or port conflict messages.
echo.
echo [INFO] Suggested Swagger checks after gateways are up:
echo        http://127.0.0.1:18081/docs
echo        http://127.0.0.1:18081/docs_local
echo        http://127.0.0.1:18081/static/swagger/index.html
echo        https://127.0.0.1:18080/docs
echo        https://127.0.0.1:18080/docs_local
echo        https://127.0.0.1:18080/static/swagger/index.html
echo.
echo [INFO] Current related processes:
tasklist | findstr /I "dvr_gateway fm_gateway message_hub dealer_gui"
echo.
pause
exit /b 0

:start_service
set "SERVICE_NAME=%~1"
set "SERVICE_EXE=%~2"

if not exist "%SERVICE_EXE%" (
    echo [ERROR] Missing executable for %SERVICE_NAME%:
    echo         %BASE_DIR%%SERVICE_EXE%
    echo.
    exit /b 1
)

echo [START] %SERVICE_NAME% - %SERVICE_EXE%
REM Keep cwd at dist root so config.env and static/ can be found by services.
start "%SERVICE_NAME%" /D "%BASE_DIR%" cmd /k ""%BASE_DIR%%SERVICE_EXE%""
exit /b 0
