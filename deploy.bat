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
echo === [4/5] NSSM restart OrinuMain ===
"%NSSM%" restart OrinuMain
if errorlevel 1 (
    echo [WARN] NSSM restart returned non-zero. Check service state manually.
)

echo Waiting 20 seconds for service to initialize...
timeout /t 20 /nobreak >nul

echo.
echo === [5/5] health check ===
curl -s -o nul -w "HTTP %%{http_code}\n" "%HEALTH_URL%"
sc query OrinuMain | findstr STATE

echo.
echo === DEPLOY DONE ===
echo Verify externally: curl -I https://factory.flickdone.com/api/v1/local/health
endlocal
