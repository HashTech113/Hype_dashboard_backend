<#
.SYNOPSIS
    Launch AI Camera Surveillance as a native-feeling desktop app.

.DESCRIPTION
    Detects the best available browser (Edge → Chrome → Brave → default)
    and launches http://localhost:3000 in `--app=` mode — a chromeless
    window with no address bar, no tabs, no extensions toolbar. With the
    custom icon attached via the shortcut, the result is visually and
    functionally indistinguishable from a native Windows application:

      * Custom title bar + icon
      * Custom taskbar icon (not the browser's)
      * Resizable / snappable like any app window
      * Pinnable to taskbar / Start
      * Alt+Tab shows it as its own app

    Why not Electron / Tauri / WebView2 wrapper?
      - Edge is preinstalled on every Win10/11 box (no extra runtime)
      - Zero bundled size — just a shortcut
      - The chromeless behaviour is identical to what those frameworks
        ultimately produce (they're all Chromium under the hood)

    Boot-wait logic: if the user double-clicks the icon immediately after
    a fresh install, the backend services may still be starting (NSSM
    boot takes ~5-10 s). We poll /health for up to 30 s before launching
    so the user never sees ERR_CONNECTION_REFUSED.
#>

$ErrorActionPreference = "Continue"
$BackendHealth = "http://127.0.0.1:8000/health"
$AppUrl = "http://localhost:3000"

# ---- 1. Locate a Chromium-based browser ---------------------------------
$candidates = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Microsoft\Edge\Application\msedge.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe"
)
$browser = $null
foreach ($c in $candidates) {
    if (Test-Path $c) {
        $browser = $c
        break
    }
}

# ---- 2. Wait for the backend ---------------------------------------------
# Quick check first — if backend is already running we proceed immediately.
# Only show "Starting…" splash if we actually have to wait.
$ready = $false
try {
    $r = Invoke-WebRequest -Uri $BackendHealth -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ready = $true }
} catch {}

if (-not $ready) {
    # Show a tiny WinForms splash so the user knows something's happening
    # while NSSM brings the services up. Auto-closes when /health is 200.
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $splash = New-Object System.Windows.Forms.Form
    $splash.Text = "AI Camera Surveillance"
    $splash.Size = New-Object System.Drawing.Size(380, 140)
    $splash.StartPosition = "CenterScreen"
    $splash.FormBorderStyle = "FixedDialog"
    $splash.MaximizeBox = $false
    $splash.MinimizeBox = $false
    $splash.TopMost = $true
    $splash.BackColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
    $splash.ForeColor = [System.Drawing.Color]::White

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "AI Camera Surveillance"
    $title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 12)
    $title.AutoSize = $false
    $title.TextAlign = "MiddleCenter"
    $title.Dock = "Top"
    $title.Height = 40
    $splash.Controls.Add($title)

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "Starting services, this takes ~10 seconds…"
    $status.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $status.AutoSize = $false
    $status.TextAlign = "MiddleCenter"
    $status.Dock = "Fill"
    $status.ForeColor = [System.Drawing.Color]::FromArgb(180, 200, 230)
    $splash.Controls.Add($status)

    $splash.Show()
    $splash.Refresh()

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $BackendHealth -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.Application]::DoEvents()
    }
    $splash.Close()

    if (-not $ready) {
        [System.Windows.Forms.MessageBox]::Show(
            "The AI Camera Surveillance backend isn't responding.`n`n" +
            "Open Services (services.msc) and check that 'AISurveillanceBackend' " +
            "is running. If it's not, right-click it and select Start.",
            "AI Camera Surveillance",
            "OK",
            "Warning"
        )
        exit 1
    }
}

# ---- 3. Launch in app-mode --------------------------------------------
if ($browser) {
    # --app= gives a chromeless window. --window-size sets initial size.
    # --user-data-dir keeps the app's profile separate from the operator's
    # regular browsing profile (so no shared cookies, no "you're signed in
    # to Gmail in this window" confusion).
    $userDataDir = Join-Path $env:LOCALAPPDATA "AICameraSurveillance\BrowserData"
    if (-not (Test-Path $userDataDir)) {
        New-Item -ItemType Directory -Force -Path $userDataDir | Out-Null
    }
    Start-Process -FilePath $browser -ArgumentList @(
        "--app=$AppUrl",
        "--user-data-dir=$userDataDir",
        "--window-size=1440,900",
        "--no-first-run",
        "--no-default-browser-check"
    )
} else {
    # No Chromium browser found — fall back to the system default browser.
    # User loses the chromeless look but the app still works.
    Start-Process -FilePath $AppUrl
}
