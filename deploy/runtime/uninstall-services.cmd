@echo off
REM Uninstall the AI Camera Surveillance Windows Services.
REM Must be run as Administrator.

setlocal EnableDelayedExpansion
net session >nul 2>&1
if errorlevel 1 (
    echo This script must be run as Administrator.
    pause
    exit /b 1
)

set "NSSM=%~dp0nssm\nssm.exe"
set "REPO_ROOT=%~dp0..\.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd >nul
set "STORAGE_DIR=%REPO_ROOT%\backend\storage"
set "AUDIT_DIR=%REPO_ROOT%\backend\storage\audit"
set "AUDIT_LOG=%REPO_ROOT%\dpdp_uninstall_audit.log"

echo Stopping services...
net stop AISurveillanceFrontend 2>nul
net stop AISurveillanceBackend 2>nul

echo Removing services...
"%NSSM%" remove AISurveillanceFrontend confirm 2>nul
"%NSSM%" remove AISurveillanceBackend confirm 2>nul

echo.
echo ============================================================
echo  DPDP Act 2023 Section 8 - Biometric Data Retention Notice
echo ============================================================
echo.
echo The backend\storage directory contains BIOMETRIC personal data:
echo   - Face embeddings (training_images\)
echo   - Snapshots (snapshots\)
echo   - Unknown face captures (unknowns\)
echo   - Model artifacts (models\)
echo.
echo Path: %STORAGE_DIR%
echo.
echo Under DPDP Act 2023 Section 8(7), personal data must be erased
echo once the purpose for processing is no longer being served.
echo.

if not exist "%STORAGE_DIR%" (
    echo Storage directory not found. Nothing to purge.
    goto :done
)

set "PURGE_CHOICE="
set /p "PURGE_CHOICE=Do you want to DELETE biometric data and snapshots now? (Y/n): "
if /I "!PURGE_CHOICE!"=="Y" goto :purge
if /I "!PURGE_CHOICE!"=="YES" goto :purge

echo.
echo Data retained at: %STORAGE_DIR%
echo OPERATOR RESPONSIBILITY: You must manually delete or securely archive
echo this directory to remain compliant with DPDP Act 2023 Section 8(7).
echo See DEPLOYMENT.md Section 13 (Compliance) for guidance.
echo.

REM Write DPDP audit trail entry (retention decision)
for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do set "TODAY=%%a-%%b-%%c"
for /f "tokens=1-3 delims=:., " %%a in ("%TIME%") do set "NOW=%%a-%%b-%%c"
>>"%AUDIT_LOG%" echo [%TODAY% %NOW%] UNINSTALL: services removed; biometric data RETAINED at "%STORAGE_DIR%" by operator "%USERNAME%" on host "%COMPUTERNAME%"
goto :done

:purge
echo.
echo Purging biometric data from %STORAGE_DIR% ...
REM Preserve audit directory if it exists (immutable audit trail under DPDP Sec 8/21)
if exist "%AUDIT_DIR%" (
    echo Preserving audit subdirectory: %AUDIT_DIR%
    set "AUDIT_BACKUP=%REPO_ROOT%\dpdp_audit_preserved"
    if not exist "!AUDIT_BACKUP!" mkdir "!AUDIT_BACKUP!"
    xcopy /E /I /Y /Q "%AUDIT_DIR%" "!AUDIT_BACKUP!" >nul
)

rmdir /S /Q "%STORAGE_DIR%\training_images" 2>nul
rmdir /S /Q "%STORAGE_DIR%\snapshots" 2>nul
rmdir /S /Q "%STORAGE_DIR%\unknowns" 2>nul
rmdir /S /Q "%STORAGE_DIR%\embeddings" 2>nul
rmdir /S /Q "%STORAGE_DIR%\previews" 2>nul

REM Write DPDP audit trail entry (purge action)
for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do set "TODAY=%%a-%%b-%%c"
for /f "tokens=1-3 delims=:., " %%a in ("%TIME%") do set "NOW=%%a-%%b-%%c"
>>"%AUDIT_LOG%" echo [%TODAY% %NOW%] UNINSTALL: services removed; biometric data PURGED from "%STORAGE_DIR%" by operator "%USERNAME%" on host "%COMPUTERNAME%"

echo Biometric data purged.
echo DPDP audit entry written to: %AUDIT_LOG%

:done
echo.
echo Done. Services have been uninstalled.
pause
endlocal
