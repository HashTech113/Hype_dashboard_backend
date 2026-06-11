@echo off
REM ================================================================
REM  AI Camera Surveillance — Windows Service installer
REM
REM  Run this as Administrator (right-click → Run as administrator).
REM  Registers two auto-restart Windows Services backed by NSSM:
REM
REM    AISurveillanceBackend   — FastAPI + InsightFace + go2rtc on :8000
REM    AISurveillanceFrontend  — Next.js production server on :3000
REM
REM  After install, both services auto-start on boot, restart on
REM  crash, and write logs to .\logs\. Stop them with:
REM
REM    net stop AISurveillanceFrontend
REM    net stop AISurveillanceBackend
REM
REM  Uninstall with:
REM
REM    uninstall-services.cmd  (next to this script, also admin)
REM ================================================================

setlocal ENABLEDELAYEDEXPANSION

REM --- Must be admin --------------------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: This script must be run as Administrator.
    echo  Right-click install-services.cmd then "Run as administrator".
    echo.
    pause
    exit /b 1
)

REM --- Resolve absolute paths so the services don't depend on CWD ----
set "DEPLOY_DIR=%~dp0"
for %%i in ("%DEPLOY_DIR%..\..") do set "PROJECT_DIR=%%~fi"
set "NSSM=%DEPLOY_DIR%nssm\nssm.exe"
set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NEXT_BIN=%FRONTEND_DIR%\node_modules\next\dist\bin\next"

REM --- Locate Node.js for the frontend service -----------------------
set "NODE_EXE="
where node >nul 2>&1 && for /f "delims=" %%i in ('where node') do (
    if not defined NODE_EXE set "NODE_EXE=%%i"
)
if not defined NODE_EXE (
    if exist "C:\Program Files\nodejs\node.exe" set "NODE_EXE=C:\Program Files\nodejs\node.exe"
)
if not defined NODE_EXE (
    echo.
    echo  ERROR: node.exe not found in PATH or "C:\Program Files\nodejs\".
    echo  Install Node.js 20+ from https://nodejs.org and re-run this script.
    echo.
    pause
    exit /b 1
)

REM --- Sanity checks --------------------------------------------------
if not exist "%NSSM%" (
    echo ERROR: NSSM not found at "%NSSM%"
    pause
    exit /b 1
)
if not exist "%PYTHON%" (
    echo ERROR: backend venv missing. Create it: python -m venv backend\.venv ^&^& backend\.venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)
if not exist "%FRONTEND_DIR%\.next" (
    echo ERROR: frontend not built. Run: cd frontend ^&^& npm run build
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM --- Detect installed PostgreSQL Windows Service -------------------
REM  The backend must wait for PostgreSQL to be ready before it starts,
REM  otherwise the first DB connection after a reboot races against
REM  Postgres recovery and the readiness endpoint returns 503 for ~30s.
REM  Probe known service names (PostgreSQL-x64-12..17, postgresql-x64-*)
REM  and pick the first one that exists. If none found, warn the operator.
set "PG_SERVICE="
for %%V in (17 16 15 14 13 12) do (
    if not defined PG_SERVICE (
        sc query "postgresql-x64-%%V" >nul 2>&1
        if not errorlevel 1 set "PG_SERVICE=postgresql-x64-%%V"
    )
    if not defined PG_SERVICE (
        sc query "PostgreSQL-x64-%%V" >nul 2>&1
        if not errorlevel 1 set "PG_SERVICE=PostgreSQL-x64-%%V"
    )
)
if not defined PG_SERVICE (
    echo.
    echo  WARNING: No PostgreSQL Windows Service detected (postgresql-x64-12..17).
    echo  The backend will be installed WITHOUT a Postgres dependency. On reboot
    echo  the backend may fail its first DB connection if Postgres is still
    echo  initializing. Install PostgreSQL as a Windows Service and re-run this
    echo  script, OR ensure PostgreSQL is started before AISurveillanceBackend.
    echo.
)

echo.
echo  Installing AISurveillanceBackend service...
echo  --------------------------------------
"%NSSM%" install AISurveillanceBackend "%PYTHON%" "-m" "uvicorn" "app.main:app" "--host" "127.0.0.1" "--port" "8000" "--workers" "1" "--log-level" "warning" "--no-access-log" "--proxy-headers" >nul
"%NSSM%" set AISurveillanceBackend AppDirectory "%BACKEND_DIR%" >nul
"%NSSM%" set AISurveillanceBackend Start SERVICE_AUTO_START >nul
if defined PG_SERVICE (
    "%NSSM%" set AISurveillanceBackend DependOnService "%PG_SERVICE%" >nul
    echo   depending on %PG_SERVICE%
)
"%NSSM%" set AISurveillanceBackend AppStdout "%LOG_DIR%\backend.log" >nul
"%NSSM%" set AISurveillanceBackend AppStderr "%LOG_DIR%\backend.log" >nul
"%NSSM%" set AISurveillanceBackend AppRotateFiles 1 >nul
"%NSSM%" set AISurveillanceBackend AppRotateBytes 104857600 >nul
"%NSSM%" set AISurveillanceBackend AppExit Default Restart >nul
"%NSSM%" set AISurveillanceBackend AppThrottle 5000 >nul
"%NSSM%" set AISurveillanceBackend Description "AI Camera Surveillance — FastAPI + face recognition + go2rtc" >nul
echo  installed.

echo.
echo  Installing AISurveillanceFrontend service...
echo  ---------------------------------------
"%NSSM%" install AISurveillanceFrontend "%NODE_EXE%" "%NEXT_BIN%" "start" "--hostname" "127.0.0.1" "--port" "3000" >nul
"%NSSM%" set AISurveillanceFrontend AppDirectory "%FRONTEND_DIR%" >nul
"%NSSM%" set AISurveillanceFrontend Start SERVICE_AUTO_START >nul
"%NSSM%" set AISurveillanceFrontend DependOnService AISurveillanceBackend >nul
"%NSSM%" set AISurveillanceFrontend AppStdout "%LOG_DIR%\frontend.log" >nul
"%NSSM%" set AISurveillanceFrontend AppStderr "%LOG_DIR%\frontend.log" >nul
"%NSSM%" set AISurveillanceFrontend AppRotateFiles 1 >nul
"%NSSM%" set AISurveillanceFrontend AppRotateBytes 104857600 >nul
"%NSSM%" set AISurveillanceFrontend AppExit Default Restart >nul
"%NSSM%" set AISurveillanceFrontend AppEnvironmentExtra "NODE_ENV=production" >nul
"%NSSM%" set AISurveillanceFrontend Description "AI Camera Surveillance — Next.js production server" >nul
echo  installed.

echo.
echo  Stopping any foreground processes from this session...
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *uvicorn*" >nul 2>&1
taskkill /F /FI "IMAGENAME eq node.exe" /FI "WINDOWTITLE eq *next*" >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo  Starting services...
net start AISurveillanceBackend
if errorlevel 1 (
    echo  ERROR: backend service failed to start. Check "%LOG_DIR%\backend.log"
    pause
    exit /b 1
)
net start AISurveillanceFrontend
if errorlevel 1 (
    echo  ERROR: frontend service failed to start. Check "%LOG_DIR%\frontend.log"
    pause
    exit /b 1
)

echo.
echo  =================================================
echo   AI Camera Surveillance is now running as a
echo   Windows Service. Open http://localhost:3000
echo   in your browser.
echo.
echo   The services auto-start on every reboot and
echo   restart automatically if they crash.
echo.
echo   To stop:       net stop AISurveillanceFrontend ^&^& net stop AISurveillanceBackend
echo   To uninstall:  uninstall-services.cmd  (admin)
echo  =================================================
echo.
pause
endlocal
