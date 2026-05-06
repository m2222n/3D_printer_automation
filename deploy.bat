@echo off
REM ============================================================================
REM  Orinu Factory PC Deploy Script
REM  Location: D:\3D_printer_automation_0305\3D_printer_automation\deploy.bat
REM
REM  Run as: Administrator cmd in this directory
REM    cd /d D:\3D_printer_automation_0305\3D_printer_automation
REM    deploy.bat
REM
REM  Steps:
REM    1) git pull --ff-only origin main   (no merge commits, abort if diverged)
REM    2) pip install -r requirements.txt  (sync new dependencies)
REM    3) frontend npm install + build      (rebuild static assets)
REM    4) NSSM restart OrinuMain            (apply changes)
REM    5) wait + health check
REM
REM  On any failure the script aborts WITHOUT restarting the service so the
REM  currently-running version stays up.
REM ============================================================================

setlocal enabledelayedexpansion
set REPO_ROOT=D:\3D_printer_automation_0305\3D_printer_automation
set NSSM=C:\nssm\nssm-2.24\win64\nssm.exe
set HEALTH_URL=http://127.0.0.1:8085/api/v1/local/health

cd /d "%REPO_ROOT%" || ( echo [ABORT] cannot cd to %REPO_ROOT% & exit /b 1 )

echo.
echo === [1/5] git pull --ff-only origin main ===
git fetch origin main || ( echo [ABORT] git fetch failed & exit /b 1 )
git pull --ff-only origin main
if errorlevel 1 (
    echo [ABORT] fast-forward failed. Local branch diverged from origin/main.
    echo         Resolve manually before retrying. Service NOT restarted.
    exit /b 1
)

echo.
echo === [2/5] pip install -r requirements.txt ===
call .venv\Scripts\activate.bat || ( echo [ABORT] venv activate failed & exit /b 1 )
pip install -r requirements.txt
if errorlevel 1 (
    echo [ABORT] pip install failed. Service NOT restarted.
    exit /b 1
)

echo.
echo === [3/5] frontend npm install + build ===
pushd frontend
call npm install
if errorlevel 1 (
    echo [ABORT] npm install failed. Service NOT restarted.
    popd
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo [ABORT] npm run build failed. Service NOT restarted.
    popd
    exit /b 1
)
popd

echo.
echo === [4/5] NSSM restart OrinuMain (with zombie cleanup) ===
echo Stopping OrinuMain...
"%NSSM%" stop OrinuMain
timeout /t 3 /nobreak >nul

REM ===== 좀비 정리 =====
REM NSSM stop 후 남는 Python 좀비 처리. file_receiver.py(8089)와 sequence_service
REM 자식 process는 NSSM이 다시 띄워주므로 모두 종료해도 안전.
REM 단, Console session(태민님 직접 띄운 것) 세션은 보존.
echo Cleaning Python zombies (Services session only)...
for /f "tokens=2,4" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO TABLE /NH 2^>nul') do (
    if "%%b"=="Services" (
        echo   - taskkill PID %%a
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul

echo Starting OrinuMain...
"%NSSM%" start OrinuMain
if errorlevel 1 (
    echo [WARN] NSSM start returned non-zero. Check service state manually.
)

echo Waiting 20 seconds for service to initialize...
timeout /t 20 /nobreak >nul

echo.
echo === [5/5] health check ===
curl -s -o nul -w "HTTP %%{http_code}\n" "%HEALTH_URL%"
sc query OrinuMain | findstr STATE

REM 8085 LISTEN PID가 .venv python인지 검증
echo.
echo === venv check (PID using port 8085) ===
for /f "tokens=5" %%p in ('netstat -ano ^| findstr LISTENING ^| findstr ":8085"') do (
    wmic process where "ProcessId=%%p" get ExecutablePath /value 2>nul | findstr "ExecutablePath"
)

echo.
echo === DEPLOY DONE ===
echo Verify externally: curl -I https://factory.flickdone.com/api/v1/local/health
endlocal
