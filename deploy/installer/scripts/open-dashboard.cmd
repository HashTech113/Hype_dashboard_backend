@echo off
REM Operator shortcut — opens the surveillance dashboard.
REM Waits a couple of seconds in case the services are still starting.
timeout /t 2 /nobreak >nul 2>&1
start "" "http://localhost:3000"
