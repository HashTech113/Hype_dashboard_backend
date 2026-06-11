@echo off
REM ================================================================
REM  AI Camera Surveillance — One-command installer builder
REM
REM  Run this from the project root. It does the complete pipeline:
REM    1. Builds the Next.js production bundle
REM    2. Stages all assets (Node, NSSM, go2rtc, Postgres, VC++)
REM    3. Compiles the Inno Setup .iss into Setup.exe
REM
REM  Output: deploy\installer\output\AICameraSurveillance-Setup-X.Y.Z.exe
REM         ~900 MB single-click installer that bundles everything the
REM         end-user needs: Postgres, Node, Python, runtime libs, models,
REM         frontend assets, backend code.
REM
REM  Prerequisites on the BUILD machine (not the target):
REM    - Inno Setup 6.x (https://jrsoftware.org/isdl.php)
REM    - Python 3.11+ with venv already created in backend\.venv
REM    - Node 20+ with npm
REM    - Internet (to download the bundled prereqs the first time)
REM
REM  First build ~15 minutes (downloads + venv copy + npm build).
REM  Subsequent builds ~3 minutes (.downloads cache hits).
REM ================================================================

setlocal ENABLEDELAYEDEXPANSION

set "ROOT=%~dp0.."
set "INSTALLER_DIR=%~dp0installer"
pushd "%ROOT%"

REM ----------------------------------------------------------------
REM  Parse optional flags:
REM    --skip-build  : skip Step 2 (Next.js production build)
REM    --skip-stage  : skip Step 3 (stage-assets.ps1 — downloads + copies)
REM    --help / -h   : print usage
REM  Use these to iterate quickly when only the .iss has changed.
REM ----------------------------------------------------------------
set "SKIP_BUILD=0"
set "SKIP_STAGE=0"
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--skip-build" ( set "SKIP_BUILD=1" & shift & goto parse_args )
if /I "%~1"=="--skip-stage" ( set "SKIP_STAGE=1" & shift & goto parse_args )
if /I "%~1"=="--help"       ( goto show_help )
if /I "%~1"=="-h"           ( goto show_help )
echo  ERROR: Unknown argument: %~1
echo  Use --help for usage.
popd
exit /b 1
:show_help
echo.
echo  Usage: build.cmd [--skip-build] [--skip-stage]
echo.
echo    --skip-build   Skip Next.js production build (Step 2)
echo    --skip-stage   Skip asset staging / downloads (Step 3)
echo.
echo  Default (no flags): full build pipeline (all 4 steps).
echo  Example: build.cmd --skip-stage --skip-build
echo           ^(only re-compiles the Inno Setup .iss^)
echo.
popd
exit /b 0
:args_done

echo.
echo ================================================================
echo  AI Camera Surveillance — Build Pipeline
echo ================================================================
echo.
echo  Project root: %ROOT%
if "%SKIP_BUILD%"=="1" echo  Flag: --skip-build  ^(Step 2 will be skipped^)
if "%SKIP_STAGE%"=="1" echo  Flag: --skip-stage  ^(Step 3 will be skipped^)
echo.

REM ----------------------------------------------------------------
REM  Step 1: Pre-flight checks
REM ----------------------------------------------------------------
echo [1/4] Pre-flight checks...

if not exist "backend\.venv\Scripts\python.exe" (
    echo.
    echo  ERROR: backend\.venv missing.
    echo  Create it first:
    echo    cd backend
    echo    python -m venv .venv
    echo    .venv\Scripts\pip install -r requirements.txt
    echo.
    popd
    exit /b 1
)
echo   - backend venv  OK

where node >nul 2>&1
if errorlevel 1 (
    echo  ERROR: node not found in PATH. Install Node 20+.
    popd
    exit /b 1
)
echo   - node          OK

REM Try to find Inno Setup compiler (ISCC.exe)
set "ISCC="
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) do (
    if exist "%%~P" set "ISCC=%%~P"
)
if not defined ISCC (
    echo.
    echo  WARNING: Inno Setup Compiler (ISCC.exe) not found.
    echo  Steps 1-3 will still run (build + stage), but you'll need to
    echo  open .iss manually in Inno Setup Compiler at the end.
    echo  Download: https://jrsoftware.org/isdl.php
    echo.
)
if defined ISCC echo   - Inno Setup    OK ^(%ISCC%^)

REM ----------------------------------------------------------------
REM  Step 2: Frontend production build
REM ----------------------------------------------------------------
echo.
if "%SKIP_BUILD%"=="1" (
    echo [2/4] Skipping Next.js production build ^(--skip-build^).
    if not exist "frontend\.next" (
        echo  WARNING: frontend\.next does not exist. The installer will be
        echo  built without a fresh frontend bundle. Remove --skip-build to
        echo  produce a complete installer.
    )
) else (
    echo [2/4] Building Next.js production bundle...
    pushd frontend
    if not exist node_modules (
        echo   First-time install of frontend deps...
        call npm ci --no-audit --no-fund
        if errorlevel 1 ( popd & popd & exit /b 1 )
    )
    call npm run build
    if errorlevel 1 ( popd & popd & exit /b 1 )
    popd
    echo   - frontend\.next built  OK
)

REM ----------------------------------------------------------------
REM  Step 3: Stage assets (downloads if needed)
REM ----------------------------------------------------------------
echo.
if "%SKIP_STAGE%"=="1" (
    echo [3/4] Skipping asset staging ^(--skip-stage^).
) else (
    echo [3/4] Staging assets ^(Node, NSSM, go2rtc, Postgres, VC++^)...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER_DIR%\stage-assets.ps1"
    if errorlevel 1 (
        echo  ERROR: stage-assets.ps1 failed.
        popd
        exit /b 1
    )
)

REM ----------------------------------------------------------------
REM  Step 4: Compile the Inno Setup script -> Setup.exe
REM ----------------------------------------------------------------
echo.
echo [4/4] Compiling Inno Setup...

if not defined ISCC (
    echo   SKIPPED. To finish: open
    echo     %INSTALLER_DIR%\AICameraSurveillance.iss
    echo   in Inno Setup Compiler and click Build.
    popd
    exit /b 0
)

"%ISCC%" "%INSTALLER_DIR%\AICameraSurveillance.iss"
if errorlevel 1 (
    echo  ERROR: Inno Setup compilation failed. See output above.
    popd
    exit /b 1
)

echo.
echo ================================================================
echo  BUILD COMPLETE
echo ================================================================
for %%F in ("%INSTALLER_DIR%\output\*.exe") do (
    set "SIZE=%%~zF"
    set /a SIZE_MB=!SIZE!/1048576
    echo.
    echo  Setup.exe:    %%~nxF
    echo  Size:         !SIZE_MB! MB
    echo  Location:     %%~fF
)
echo.
echo  To deploy: copy Setup.exe to the target machine and double-click.
echo  The end-user experience is fully unattended — no manual steps.
echo.
popd
endlocal
