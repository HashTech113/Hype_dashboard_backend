@echo off
REM Manual service start (the installer also auto-starts them on install)
net start AISurveillanceBackend
net start AISurveillanceFrontend
echo Done. Open http://localhost:3000
pause
