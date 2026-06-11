<#
.SYNOPSIS
    Daily automated backup of the AI CCTV Attendance database and storage.

.DESCRIPTION
    Performs:
      1. pg_dump in custom (binary) format — small, fast restore
      2. Encrypts the dump with 7-Zip AES-256 (if 7z.exe present)
      3. Copies the encrypted file to the configured backup target
      4. Rotates old backups (keeps last $RetentionDays days)
      5. Writes a one-line audit record to backup.log

    The backup is consistent — pg_dump takes a transactional snapshot, so
    the database can keep serving requests during the backup.

    Storage files (snapshots, training images, unknown captures) are NOT
    backed up by this script — they're large and re-creatable. If you want
    to back them up too, use robocopy on $StorageDir to the same target;
    see comments at the bottom.

    Schedule via Windows Task Scheduler:
      schtasks /Create /SC DAILY /TN "AIAttendanceBackup" `
        /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\backup.ps1" `
        /ST 02:00 /RL HIGHEST

    Resolves P0.2 — no automated DB backup.

.PARAMETER ProjectRoot
    Absolute path to the repo root. Default = parent of this script.

.PARAMETER BackupTarget
    Where to write the backup file. Default = $ProjectRoot\backups. Use a
    network share or external drive in production.

.PARAMETER RetentionDays
    Keep this many days of backups; older are deleted. Default 30.

.PARAMETER EncryptionPassword
    7-Zip AES-256 password for at-rest encryption. If omitted, the dump is
    not encrypted (NOT recommended — DPDP biometric data).

.PARAMETER PgDumpPath
    Path to pg_dump.exe. Default tries to discover from PG installation.

.PARAMETER DbName
    Database to dump. Default: ai_attendance.

.PARAMETER DbUser
    Postgres user. Default: postgres.

.PARAMETER PgPassword
    Postgres password. Sourced from environment PGPASSWORD if omitted. NEVER
    commit credentials to the repo — store them in a separate vault and pass
    via the scheduled-task command line.

.EXAMPLE
    .\backup.ps1
    .\backup.ps1 -BackupTarget "\\NAS\backups\ai-attendance" -EncryptionPassword "S3cret"
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$BackupTarget = "",
    [int]$RetentionDays = 30,
    [string]$EncryptionPassword = "",
    [string]$PgDumpPath = "",
    [string]$DbName = "ai_attendance",
    [string]$DbUser = "postgres",
    [string]$PgPassword = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path $ProjectRoot).Path

if (-not $BackupTarget) {
    $BackupTarget = Join-Path $ProjectRoot "backups"
}
if (-not (Test-Path $BackupTarget)) {
    New-Item -ItemType Directory -Path $BackupTarget -Force | Out-Null
}

$logFile = Join-Path $BackupTarget "backup.log"

function Write-Log($Level, $Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz') [$Level] $Message"
    Add-Content -Path $logFile -Value $line -Encoding utf8
    Write-Host $line
}

# Discover pg_dump if not given
if (-not $PgDumpPath) {
    $candidates = @(
        "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        "C:\Program Files\PostgreSQL\15\bin\pg_dump.exe",
        "C:\Program Files\PostgreSQL\14\bin\pg_dump.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $PgDumpPath = $c; break }
    }
}
if (-not $PgDumpPath -or -not (Test-Path $PgDumpPath)) {
    Write-Log "ERROR" "pg_dump.exe not found. Pass -PgDumpPath or install PostgreSQL."
    exit 1
}

# Pass PG password via env var (libpq convention)
if ($PgPassword) {
    $env:PGPASSWORD = $PgPassword
}
if (-not $env:PGPASSWORD) {
    Write-Log "WARN" "PGPASSWORD not set; pg_dump will prompt (will fail under Scheduled Task)."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpFile = Join-Path $BackupTarget "ai-attendance-$timestamp.dump"

Write-Log "INFO" "Starting backup -> $dumpFile"

try {
    & $PgDumpPath -U $DbUser -h localhost -p 5432 -Fc -f $dumpFile $DbName
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump exited with code $LASTEXITCODE"
    }
} catch {
    Write-Log "ERROR" "pg_dump failed: $_"
    exit 2
}

$dumpSize = (Get-Item $dumpFile).Length
Write-Log "INFO" "Dump complete: $([math]::Round($dumpSize / 1MB, 2)) MB"

# Encrypt if password provided
if ($EncryptionPassword) {
    $sevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if (-not $sevenZip) {
        $sevenZip = Get-Item "C:\Program Files\7-Zip\7z.exe" -ErrorAction SilentlyContinue
    }
    if ($sevenZip) {
        $encFile = "$dumpFile.7z"
        & $sevenZip.Source a -t7z "$encFile" "$dumpFile" "-p$EncryptionPassword" -mhe=on | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Remove-Item $dumpFile -Force
            Write-Log "INFO" "Encrypted -> $encFile"
        } else {
            Write-Log "WARN" "7-Zip encryption failed; leaving raw dump."
        }
    } else {
        Write-Log "WARN" "7-Zip not found; backup is UNENCRYPTED."
    }
}

# Rotate
$cutoff = (Get-Date).AddDays(-1 * $RetentionDays)
$deleted = 0
Get-ChildItem -Path $BackupTarget -Filter "ai-attendance-*" | Where-Object {
    $_.LastWriteTime -lt $cutoff -and $_.Name -ne "backup.log"
} | ForEach-Object {
    try { Remove-Item $_.FullName -Force; $deleted++ } catch { Write-Log "WARN" "Could not remove $($_.Name): $_" }
}
if ($deleted -gt 0) {
    Write-Log "INFO" "Rotated $deleted backups older than $RetentionDays days"
}

Write-Log "INFO" "Backup OK"

# -----------------------------------------------------------------------
# OPTIONAL — back up storage/ too. Uncomment to enable.
# Note: storage/ holds biometric face images under DPDP — must be encrypted
# at rest if you copy it offsite.
# -----------------------------------------------------------------------
# $storageSrc = Join-Path $ProjectRoot "backend\storage"
# $storageDst = Join-Path $BackupTarget "storage"
# if (Test-Path $storageSrc) {
#     Write-Log "INFO" "Mirroring storage/ to $storageDst"
#     robocopy $storageSrc $storageDst /MIR /R:2 /W:5 /LOG+:"$logFile" /NP /NDL
# }
