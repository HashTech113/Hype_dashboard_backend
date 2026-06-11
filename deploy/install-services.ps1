<#
.SYNOPSIS
    Install the AI CCTV Attendance backend + frontend as auto-restart Windows
    services via NSSM (Non-Sucking Service Manager).

.DESCRIPTION
    Run this ONCE on the target Windows 10/11 machine as an Administrator.
    After it completes:
      - "AI Attendance Backend" service runs uvicorn on 127.0.0.1:8000
      - "AI Attendance Frontend" service runs `next start` on 127.0.0.1:3000
      - Both auto-start on boot
      - Both restart automatically if they crash
      - Logs are appended to .\logs\service-backend.log / service-frontend.log

    Prerequisites:
      - NSSM installed at C:\nssm\nssm.exe (download from https://nssm.cc/download)
      - Python 3.11 in PATH
      - Node.js 22 LTS in PATH
      - Backend venv set up (`backend\.venv\Scripts\python.exe` exists)
      - Frontend built (`frontend\.next` exists)
      - PostgreSQL installed as a Windows Service

    Resolves P0.1 — no process supervisor, no auto-restart.

.PARAMETER ProjectRoot
    Absolute path to the repo root (the folder containing backend\ and frontend\).
    Defaults to the parent of the deploy\ folder.

.PARAMETER NssmPath
    Path to nssm.exe. Default C:\nssm\nssm.exe.

.PARAMETER Force
    Remove existing services and reinstall them.

.EXAMPLE
    .\install-services.ps1
    .\install-services.ps1 -Force
    .\install-services.ps1 -ProjectRoot "D:\ai-attendance" -NssmPath "C:\nssm\nssm.exe"
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$NssmPath = "C:\nssm\nssm.exe",
    [switch]$Force
)

# Require Administrator
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($currentUser)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator. Right-click PowerShell -> Run as administrator."
    exit 1
}

if (-not (Test-Path $NssmPath)) {
    Write-Error "NSSM not found at $NssmPath. Download from https://nssm.cc/download (extract win64\nssm.exe to C:\nssm\)."
    exit 1
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
Write-Host "Project root: $ProjectRoot" -ForegroundColor Cyan

$backendDir = Join-Path $ProjectRoot "backend"
$frontendDir = Join-Path $ProjectRoot "frontend"
$logsDir = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $backendDir)) { Write-Error "Backend dir not found: $backendDir"; exit 1 }
if (-not (Test-Path $frontendDir)) { Write-Error "Frontend dir not found: $frontendDir"; exit 1 }
if (-not (Test-Path "$backendDir\.venv\Scripts\python.exe")) {
    Write-Error "Backend venv not found at $backendDir\.venv. Create it first."; exit 1
}
if (-not (Test-Path "$frontendDir\.next")) {
    Write-Error "Frontend not built. Run 'npm run build' in $frontendDir first."; exit 1
}

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

$svcBackend = "AISurveillanceBackend"
$svcFrontend = "AISurveillanceFrontend"

function Remove-ServiceIfExists($name) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "Stopping + removing existing service: $name" -ForegroundColor Yellow
        & $NssmPath stop $name confirm | Out-Null
        Start-Sleep -Seconds 2
        & $NssmPath remove $name confirm | Out-Null
        Start-Sleep -Seconds 1
    }
}

if ($Force) {
    Remove-ServiceIfExists $svcBackend
    Remove-ServiceIfExists $svcFrontend
}

# -----------------------------------------------------------------------
# Install backend service
# -----------------------------------------------------------------------
Write-Host "Installing service: $svcBackend" -ForegroundColor Green
$pythonExe = "$backendDir\.venv\Scripts\python.exe"
$uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1"

& $NssmPath install $svcBackend $pythonExe $uvicornArgs | Out-Null
& $NssmPath set $svcBackend AppDirectory $backendDir | Out-Null
& $NssmPath set $svcBackend DisplayName "AI CCTV Attendance Backend" | Out-Null
& $NssmPath set $svcBackend Description "FastAPI backend for AI CCTV Attendance. Auto-restart on crash." | Out-Null
& $NssmPath set $svcBackend Start SERVICE_AUTO_START | Out-Null
& $NssmPath set $svcBackend AppStdout "$logsDir\service-backend.log" | Out-Null
& $NssmPath set $svcBackend AppStderr "$logsDir\service-backend.log" | Out-Null
& $NssmPath set $svcBackend AppRotateFiles 1 | Out-Null
& $NssmPath set $svcBackend AppRotateOnline 1 | Out-Null
& $NssmPath set $svcBackend AppRotateBytes 104857600 | Out-Null  # 100 MB
& $NssmPath set $svcBackend AppExit Default Restart | Out-Null
& $NssmPath set $svcBackend AppRestartDelay 5000 | Out-Null
& $NssmPath set $svcBackend AppThrottle 10000 | Out-Null

# -----------------------------------------------------------------------
# Install frontend service
# -----------------------------------------------------------------------
Write-Host "Installing service: $svcFrontend" -ForegroundColor Green
# Use cmd /c to chain "node node_modules\.bin\next" reliably even when next.cmd
# lives behind a junction, which NSSM doesn't always resolve. The actual JS
# entrypoint is .bin\next which spawns the standalone server.
$nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodeExe) { Write-Error "node.exe not found in PATH"; exit 1 }
$nextEntry = "$frontendDir\node_modules\next\dist\bin\next"

if (-not (Test-Path $nextEntry)) {
    Write-Error "Next.js entry not found: $nextEntry. Run 'npm install' in $frontendDir first."
    exit 1
}

& $NssmPath install $svcFrontend $nodeExe "$nextEntry start --port 3000 --hostname 127.0.0.1" | Out-Null
& $NssmPath set $svcFrontend AppDirectory $frontendDir | Out-Null
& $NssmPath set $svcFrontend DisplayName "AI CCTV Attendance Frontend" | Out-Null
& $NssmPath set $svcFrontend Description "Next.js admin UI for AI CCTV Attendance. Auto-restart on crash." | Out-Null
& $NssmPath set $svcFrontend Start SERVICE_AUTO_START | Out-Null
& $NssmPath set $svcFrontend AppStdout "$logsDir\service-frontend.log" | Out-Null
& $NssmPath set $svcFrontend AppStderr "$logsDir\service-frontend.log" | Out-Null
& $NssmPath set $svcFrontend AppRotateFiles 1 | Out-Null
& $NssmPath set $svcFrontend AppRotateOnline 1 | Out-Null
& $NssmPath set $svcFrontend AppRotateBytes 104857600 | Out-Null
& $NssmPath set $svcFrontend AppExit Default Restart | Out-Null
& $NssmPath set $svcFrontend AppRestartDelay 5000 | Out-Null
& $NssmPath set $svcFrontend AppThrottle 10000 | Out-Null
& $NssmPath set $svcFrontend AppEnvironmentExtra "NODE_ENV=production" | Out-Null

# Dependency — frontend should not start before backend (avoid 5xx on first paint)
& $NssmPath set $svcFrontend DependOnService $svcBackend | Out-Null

# -----------------------------------------------------------------------
# Start
# -----------------------------------------------------------------------
Write-Host ""
Write-Host "Starting services..." -ForegroundColor Cyan
Start-Service $svcBackend
Start-Sleep -Seconds 5
Start-Service $svcFrontend

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Get-Service $svcBackend, $svcFrontend | Format-Table Name, Status, StartType

Write-Host ""
Write-Host "Verify with:" -ForegroundColor Cyan
Write-Host "  curl http://127.0.0.1:8000/health"
Write-Host "  curl http://127.0.0.1:8000/health/ready"
Write-Host "  Start http://127.0.0.1:3000 in a browser"
Write-Host ""
Write-Host "Logs:" -ForegroundColor Cyan
Write-Host "  Backend:  $logsDir\service-backend.log"
Write-Host "  Frontend: $logsDir\service-frontend.log"
Write-Host ""
Write-Host "To stop:    nssm stop $svcBackend (and -frontend)"
Write-Host "To remove:  nssm remove $svcBackend confirm"
