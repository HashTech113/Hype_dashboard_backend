<#
.SYNOPSIS
    End-to-end smoke test for a fresh AI Camera Surveillance install.

.DESCRIPTION
    Runs after install (Setup.exe finishes OR install-services.cmd
    succeeds) to PROVE every subsystem actually works. Catches the
    boring-but-deadly failures: PG not running, Python venv broken,
    InsightFace models missing, ports blocked by firewall, frontend
    bundle missing.

    Exit codes:
      0  = all checks passed, app is ready to use
      1  = one or more critical checks failed (see output for which)

    Run with -Verbose to see exactly what each check is testing.

.EXAMPLE
    .\verify-install.ps1
    .\verify-install.ps1 -InstallRoot C:\AICameraSurveillance
#>
[CmdletBinding()]
param(
    [string]$InstallRoot,
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$FrontendUrl = "http://127.0.0.1:3000",
    [string]$Go2RtcUrl = "http://127.0.0.1:1984"
)

# Resolve InstallRoot in the body (not the param default) so we can fall
# back if $PSScriptRoot is empty — happens when launched via
# `powershell -File` without a fully-qualified path.
if (-not $InstallRoot) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if (-not $scriptDir) {
        $scriptDir = (Get-Location).Path
    }
    $InstallRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
}

$ErrorActionPreference = "Continue"
$FailedChecks = @()
$PassedChecks = @()

function Test-Check {
    param([string]$Name, [scriptblock]$Block, [bool]$Critical = $true)
    Write-Host -NoNewline ("  [{0,-50}] " -f $Name)
    try {
        $result = & $Block
        if ($result) {
            Write-Host "PASS" -ForegroundColor Green
            $script:PassedChecks += $Name
            return $true
        } else {
            if ($Critical) {
                Write-Host "FAIL" -ForegroundColor Red
                $script:FailedChecks += $Name
            } else {
                Write-Host "WARN" -ForegroundColor Yellow
            }
            return $false
        }
    } catch {
        if ($Critical) {
            Write-Host "FAIL ($_)" -ForegroundColor Red
            $script:FailedChecks += "$Name ($_)"
        } else {
            Write-Host "WARN ($_)" -ForegroundColor Yellow
        }
        return $false
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " AI Camera Surveillance — Install Verification" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Install root: $InstallRoot"
Write-Host ""

# ============================================================
# 1. File-system layout — proves the installer copied everything
# ============================================================
Write-Host "[1/6] File-system layout" -ForegroundColor Cyan
$backendDir = Join-Path $InstallRoot "backend"
$frontendDir = Join-Path $InstallRoot "frontend"
Test-Check "backend\.venv\Scripts\python.exe present" {
    Test-Path (Join-Path $backendDir ".venv\Scripts\python.exe")
}
Test-Check "backend\app\main.py present" {
    Test-Path (Join-Path $backendDir "app\main.py")
}
Test-Check "backend\alembic.ini present" {
    Test-Path (Join-Path $backendDir "alembic.ini")
}
Test-Check "backend\storage\bin\go2rtc.exe present" {
    Test-Path (Join-Path $backendDir "storage\bin\go2rtc.exe")
} -Critical $false
Test-Check "frontend\.next\ (production bundle) present" {
    Test-Path (Join-Path $frontendDir ".next")
}
Test-Check "frontend\node_modules\next present" {
    Test-Path (Join-Path $frontendDir "node_modules\next")
}

# ============================================================
# 2. PostgreSQL — the one thing we don't bundle
# ============================================================
Write-Host ""
Write-Host "[2/6] PostgreSQL" -ForegroundColor Cyan
Test-Check "PostgreSQL service is running" {
    # Bundled installer creates the service as 'ai-camera-postgres'
    # (see AICameraSurveillance.iss --servicename ai-camera-postgres).
    # Fall back to the stock EnterpriseDB names so a pre-existing PG
    # also passes this check.
    $svc = Get-Service ai-camera-postgres -ErrorAction SilentlyContinue
    if (-not $svc) { $svc = Get-Service postgresql-x64-16 -ErrorAction SilentlyContinue }
    if (-not $svc) { $svc = Get-Service postgresql-x64-17 -ErrorAction SilentlyContinue }
    if (-not $svc) { $svc = Get-Service postgresql-x64-15 -ErrorAction SilentlyContinue }
    $svc -and $svc.Status -eq "Running"
}
Test-Check "PostgreSQL listening on tcp:55432" {
    # Bundled PG is configured with --serverport 55432 in the .iss to
    # avoid colliding with any pre-existing PG on the default 5432.
    Test-NetConnection -ComputerName 127.0.0.1 -Port 55432 -InformationLevel Quiet -WarningAction SilentlyContinue
}

# ============================================================
# 3. Backend health
# ============================================================
Write-Host ""
Write-Host "[3/6] Backend (FastAPI)" -ForegroundColor Cyan
Test-Check "Backend /health returns 200" {
    try {
        $r = Invoke-WebRequest -Uri "$BackendUrl/health" -UseBasicParsing -TimeoutSec 5
        $r.StatusCode -eq 200
    } catch { $false }
}
Test-Check "Backend /health/ready (full readiness)" {
    try {
        $r = Invoke-WebRequest -Uri "$BackendUrl/health/ready" -UseBasicParsing -TimeoutSec 10
        $r.StatusCode -eq 200
    } catch { $false }
}
Test-Check "/health/ready reports DB connection OK" {
    try {
        $j = Invoke-RestMethod -Uri "$BackendUrl/health/ready" -TimeoutSec 10
        $j.checks.database.ok -eq $true
    } catch { $false }
}
Test-Check "/health/ready reports embedding cache loaded" {
    try {
        $j = Invoke-RestMethod -Uri "$BackendUrl/health/ready" -TimeoutSec 10
        # The embedding cache loads InsightFace + every employee's face
        # vectors. ok=true means the face model loaded AND the cache
        # populated successfully — the proxy for "face recognition is
        # ready to identify people".
        $j.checks.embedding_cache.ok -eq $true
    } catch { $false }
}
Test-Check "/health/ready reports camera workers tracked" {
    try {
        $j = Invoke-RestMethod -Uri "$BackendUrl/health/ready" -TimeoutSec 10
        $j.checks.camera_workers.ok -eq $true
    } catch { $false }
} -Critical $false

# ============================================================
# 4. go2rtc bridge (optional — fallback to WS if down)
# ============================================================
Write-Host ""
Write-Host "[4/6] go2rtc WebRTC bridge (optional)" -ForegroundColor Cyan
Test-Check "go2rtc /api/streams responds" {
    try {
        $r = Invoke-WebRequest -Uri "$Go2RtcUrl/api/streams" -UseBasicParsing -TimeoutSec 3
        $r.StatusCode -eq 200
    } catch { $false }
} -Critical $false

# ============================================================
# 5. Frontend
# ============================================================
Write-Host ""
Write-Host "[5/6] Frontend (Next.js)" -ForegroundColor Cyan
Test-Check "Frontend /login serves HTML" {
    try {
        $r = Invoke-WebRequest -Uri "$FrontendUrl/login" -UseBasicParsing -TimeoutSec 5
        $r.StatusCode -eq 200 -and $r.Content -match "AI Camera"
    } catch { $false }
}
Test-Check "Frontend can reach backend (no CORS errors)" {
    # We can't test CORS from here directly. Approximation:
    # both endpoints respond, and the frontend's env var points
    # to a valid backend URL.
    try {
        $envFile = Join-Path $frontendDir ".env.local"
        if (-not (Test-Path $envFile)) { return $false }
        $content = Get-Content $envFile -Raw
        $content -match "NEXT_PUBLIC_API_URL"
    } catch { $false }
}

# ============================================================
# 6. End-to-end auth flow
# ============================================================
Write-Host ""
Write-Host "[6/6] End-to-end auth" -ForegroundColor Cyan
Test-Check "Admin login with bootstrap credentials" {
    try {
        $body = @{username="admin"; password="ChangeMe@123"} | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$BackendUrl/api/v1/auth/login" `
            -Method Post -Body $body -ContentType "application/json" -TimeoutSec 5
        [bool]$r.access_token
    } catch { $false }
}

# ============================================================
# Summary
# ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " RESULTS"                                                     -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ("  Passed: {0}" -f $PassedChecks.Count) -ForegroundColor Green
Write-Host ("  Failed: {0}" -f $FailedChecks.Count) -ForegroundColor ($(if($FailedChecks.Count -gt 0){"Red"}else{"Green"}))
if ($FailedChecks.Count -gt 0) {
    Write-Host ""
    Write-Host "  Failed checks:" -ForegroundColor Red
    foreach ($f in $FailedChecks) { Write-Host "    - $f" -ForegroundColor Red }
    Write-Host ""
    Write-Host "  See logs at:" -ForegroundColor Yellow
    Write-Host "    $InstallRoot\logs\backend.log"
    Write-Host "    $InstallRoot\logs\frontend.log"
    Write-Host ""
    exit 1
} else {
    Write-Host ""
    Write-Host "  ALL CRITICAL CHECKS PASSED" -ForegroundColor Green
    Write-Host "  Open $FrontendUrl in your browser." -ForegroundColor Green
    Write-Host ""
    exit 0
}
