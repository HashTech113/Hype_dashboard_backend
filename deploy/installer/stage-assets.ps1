<#
.SYNOPSIS
    Stage all runtime assets into ./assets/ ready for Inno Setup.

.DESCRIPTION
    Inno Setup's [Files] section only copies files that already exist on
    disk at build time. This script collects them all into ./assets/:

      assets/backend/      ← Python sources + venv + models
      assets/frontend/     ← built .next + production node_modules
      assets/node/         ← portable Node.js runtime
      assets/nssm/         ← NSSM service supervisor binary

    Run this ONCE on the build machine before opening the .iss in Inno
    Setup. It takes 5-10 minutes (mainly venv + node_modules copy).

.PARAMETER ProjectRoot
    Absolute path to the repo root (the folder containing backend\ and
    frontend\). Default: the parent of deploy\.

.PARAMETER NodeUrl
    URL to portable Node.js zip. Default = Node 22 LTS Windows x64.

.PARAMETER NssmUrl
    URL to NSSM zip. Default = 2.24.

.EXAMPLE
    .\stage-assets.ps1
    .\stage-assets.ps1 -ProjectRoot D:\code\attendance
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$NodeUrl = "https://nodejs.org/dist/v22.11.0/node-v22.11.0-win-x64.zip",
    [string]$NssmUrl = "https://nssm.cc/release/nssm-2.24.zip",
    [string]$Go2RtcUrl = "https://github.com/AlexxIT/go2rtc/releases/download/v1.9.7/go2rtc_win64.zip",
    # PostgreSQL 16 LTS — bundled so the end-user has zero prerequisites.
    # The installer runs this with --mode unattended so the user never
    # sees a Postgres setup wizard. ~250 MB.
    [string]$PostgresUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64.exe",
    # Microsoft Visual C++ 2015-2022 redistributable — required by
    # OpenCV + ONNX Runtime + a few other native Python wheels.
    [string]$VcRedistUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$StagingDir = Join-Path $PSScriptRoot "assets"
$DownloadDir = Join-Path $PSScriptRoot ".downloads"

Write-Host "=== AI Camera Surveillance — staging installer assets ===" -ForegroundColor Cyan
Write-Host "Project root : $ProjectRoot"
Write-Host "Staging dir  : $StagingDir"
Write-Host ""

# --- Sanity checks ---------------------------------------------------
$backendDir = Join-Path $ProjectRoot "backend"
$frontendDir = Join-Path $ProjectRoot "frontend"
foreach ($d in @($backendDir, $frontendDir)) {
    if (-not (Test-Path $d)) {
        Write-Error "Required folder missing: $d"
        exit 1
    }
}
if (-not (Test-Path "$backendDir\.venv\Scripts\python.exe")) {
    Write-Error "Backend venv not found. Create it first: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path "$frontendDir\.next")) {
    Write-Warning ".next not found in frontend\. You probably forgot to run 'npm run build'."
    $resp = Read-Host "Continue anyway? (y/N)"
    if ($resp -ne "y") { exit 1 }
}

# --- Clean staging ---------------------------------------------------
if (Test-Path $StagingDir) {
    Write-Host "Cleaning previous staging dir…" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $StagingDir
}
New-Item -ItemType Directory -Path $StagingDir | Out-Null
New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

# --- Backend ---------------------------------------------------------
Write-Host "Staging backend (this is the slow part — venv copy)…" -ForegroundColor Green
$backendStage = Join-Path $StagingDir "backend"
New-Item -ItemType Directory -Path $backendStage | Out-Null
# Exclude PII-bearing runtime data from dev machine — snapshots, training face
# images, and clustered unknown faces are biometric data and must NEVER ship to
# a customer. The installer creates these as empty dirs via the [Dirs] section.
# Also exclude downloaded model weights (~340MB); these are pulled on first
# boot, or staged separately if an air-gap install is required.
robocopy $backendDir $backendStage /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS /XD __pycache__ tests .pytest_cache snapshots training_images unknowns models logs | Out-Null
if ($LASTEXITCODE -gt 2) { Write-Error "ROBOCOPY failed copying backend (code $LASTEXITCODE)"; exit 1 }
# Drop sensitive default .env — operator will get a fresh one
if (Test-Path "$backendStage\.env") {
    Move-Item "$backendStage\.env" "$backendStage\.env.previous" -Force
}

# --- Frontend --------------------------------------------------------
Write-Host "Staging frontend…" -ForegroundColor Green
$feStage = Join-Path $StagingDir "frontend"
New-Item -ItemType Directory -Path $feStage | Out-Null
# Production node_modules only — much smaller than dev deps
Push-Location $frontendDir
try {
    Write-Host "  Installing production-only node_modules to a temp dir…"
    $tempFe = Join-Path $env:TEMP "ai-sf-fe-prod"
    if (Test-Path $tempFe) { Remove-Item -Recurse -Force $tempFe }
    New-Item -ItemType Directory -Path $tempFe -Force | Out-Null
    Copy-Item package.json,package-lock.json $tempFe -Force
    Push-Location $tempFe
    npm ci --omit=dev --no-audit --no-fund 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "npm ci failed (code $LASTEXITCODE)"; exit 1 }
    Pop-Location
    robocopy "$tempFe\node_modules" "$feStage\node_modules" /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 2) { Write-Error "ROBOCOPY failed copying frontend node_modules (code $LASTEXITCODE)"; exit 1 }
} finally {
    Pop-Location
}
robocopy "$frontendDir\.next" "$feStage\.next" /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS /XD cache | Out-Null
if ($LASTEXITCODE -gt 2) { Write-Error "ROBOCOPY failed copying frontend .next (code $LASTEXITCODE)"; exit 1 }
Copy-Item "$frontendDir\package.json" $feStage -Force
Copy-Item "$frontendDir\next.config.mjs" $feStage -Force
if (Test-Path "$frontendDir\public") {
    robocopy "$frontendDir\public" "$feStage\public" /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 2) { Write-Error "ROBOCOPY failed copying frontend public (code $LASTEXITCODE)"; exit 1 }
}

# --- Portable Node.js ------------------------------------------------
Write-Host "Downloading portable Node.js (~30MB)…" -ForegroundColor Green
$nodeZip = Join-Path $DownloadDir "node.zip"
if (-not (Test-Path $nodeZip)) {
    try {
        Invoke-WebRequest -Uri $NodeUrl -OutFile $nodeZip
    } catch {
        Write-Error "Failed to download Node.js from $NodeUrl : $_"
        exit 1
    }
} else {
    Write-Host "  Using cached node.zip ($nodeZip)"
}
$nodeStage = Join-Path $StagingDir "node"
New-Item -ItemType Directory -Path $nodeStage | Out-Null
Expand-Archive -Path $nodeZip -DestinationPath $DownloadDir -Force
# Find the extracted node-v*-win-x64\ folder and flatten it
$nodeExtracted = Get-ChildItem $DownloadDir -Directory -Filter "node-v*-win-x64" | Select-Object -First 1
if ($nodeExtracted) {
    robocopy $nodeExtracted.FullName $nodeStage /MIR /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 2) { Write-Error "ROBOCOPY failed copying Node.js (code $LASTEXITCODE)"; exit 1 }
} else {
    Write-Error "Could not find extracted node folder."
    exit 1
}

# --- NSSM -----------------------------------------------------------
Write-Host "Downloading NSSM (~1MB)…" -ForegroundColor Green
$nssmZip = Join-Path $DownloadDir "nssm.zip"
if (-not (Test-Path $nssmZip)) {
    try {
        Invoke-WebRequest -Uri $NssmUrl -OutFile $nssmZip
    } catch {
        Write-Error "Failed to download NSSM from $NssmUrl : $_"
        exit 1
    }
} else {
    Write-Host "  Using cached nssm.zip ($nssmZip)"
}
$nssmStage = Join-Path $StagingDir "nssm"
New-Item -ItemType Directory -Path $nssmStage | Out-Null
Expand-Archive -Path $nssmZip -DestinationPath $DownloadDir -Force
$nssmExtracted = Get-ChildItem $DownloadDir -Directory -Filter "nssm-*" | Select-Object -First 1
if ($nssmExtracted) {
    Copy-Item "$($nssmExtracted.FullName)\win64\nssm.exe" $nssmStage -Force
}

# --- PostgreSQL 16 (silent-installable) ------------------------------
# Bundling the full PG installer means the end-user double-clicks our
# Setup.exe and gets the entire stack — no separate Postgres install
# step. The .iss runs this with --mode unattended on a private port so
# it doesn't conflict with any pre-existing PG on the target machine.
Write-Host "Downloading PostgreSQL 16 (~250MB, this is the heavy one)…" -ForegroundColor Green
$pgInstaller = Join-Path $DownloadDir "postgresql-installer.exe"
if (-not (Test-Path $pgInstaller)) {
    try {
        Invoke-WebRequest -Uri $PostgresUrl -OutFile $pgInstaller
    } catch {
        Write-Error "Failed to download PostgreSQL installer from $PostgresUrl : $_"
        exit 1
    }
} else {
    Write-Host "  Using cached postgresql-installer.exe ($pgInstaller)"
}
$pgStage = Join-Path $StagingDir "prereqs"
New-Item -ItemType Directory -Path $pgStage -Force | Out-Null
Copy-Item $pgInstaller "$pgStage\postgresql-installer.exe" -Force
Write-Host "  Postgres installer staged ($([math]::Round((Get-Item $pgInstaller).Length/1MB,1)) MB)"

# --- Microsoft Visual C++ 2015-2022 redistributable -------------------
Write-Host "Downloading Visual C++ Redistributable (~25MB)…" -ForegroundColor Green
$vcRedist = Join-Path $DownloadDir "vc_redist.x64.exe"
if (-not (Test-Path $vcRedist)) {
    try {
        Invoke-WebRequest -Uri $VcRedistUrl -OutFile $vcRedist
    } catch {
        Write-Error "Failed to download Visual C++ Redistributable from $VcRedistUrl : $_"
        exit 1
    }
} else {
    Write-Host "  Using cached vc_redist.x64.exe ($vcRedist)"
}
Copy-Item $vcRedist "$pgStage\vc_redist.x64.exe" -Force

# --- go2rtc (RTSP→WebRTC bridge) -------------------------------------
# Pre-staged so the backend's first boot doesn't need internet.
# Lives at backend\storage\bin\go2rtc.exe per go2rtc_service.py.
Write-Host "Downloading go2rtc (~6MB)…" -ForegroundColor Green
$go2rtcZip = Join-Path $DownloadDir "go2rtc.zip"
if (-not (Test-Path $go2rtcZip)) {
    try {
        Invoke-WebRequest -Uri $Go2RtcUrl -OutFile $go2rtcZip
    } catch {
        Write-Error "Failed to download go2rtc from $Go2RtcUrl : $_"
        exit 1
    }
} else {
    Write-Host "  Using cached go2rtc.zip ($go2rtcZip)"
}
$go2rtcStage = Join-Path $StagingDir "backend\storage\bin"
New-Item -ItemType Directory -Path $go2rtcStage -Force | Out-Null
Expand-Archive -Path $go2rtcZip -DestinationPath $DownloadDir -Force
$go2rtcExe = Get-ChildItem $DownloadDir -File -Filter "go2rtc*.exe" | Select-Object -First 1
if ($go2rtcExe) {
    Copy-Item $go2rtcExe.FullName "$go2rtcStage\go2rtc.exe" -Force
    Write-Host "  go2rtc.exe staged at $go2rtcStage\go2rtc.exe"
} else {
    Write-Warning "go2rtc.exe not found after extract — first boot will try to download it"
}

# --- Summary --------------------------------------------------------
$bytes = (Get-ChildItem $StagingDir -Recurse | Measure-Object Length -Sum).Sum
$mb = [math]::Round($bytes / 1MB, 1)
Write-Host ""
Write-Host "=== Done. Staging dir is $mb MB ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open AICameraSurveillance.iss in Inno Setup Compiler"
Write-Host "  2. Compile → output is .\output\Setup.exe"
Write-Host "  3. Test it on a clean Windows VM before shipping"
Write-Host ""
Write-Host "Reminders:" -ForegroundColor Yellow
Write-Host "  · PostgreSQL 16 IS bundled and will be automatically installed"
Write-Host "    by Setup.exe (silent --mode unattended on private port 55432)."
Write-Host "    The end user does NOT need to pre-install Postgres."
Write-Host "  · The InsightFace models will be downloaded on first boot"
Write-Host "    UNLESS you copied .\backend\storage\models\* into staging."
Write-Host "    That folder is ~340MB; bundle it if you want zero-internet"
Write-Host "    install."
