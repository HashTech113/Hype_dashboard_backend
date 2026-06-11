# AI Camera Surveillance — Windows Installer Build

This directory builds a single-click Windows installer (`Setup.exe`) that
ships the entire stack:

  - Python 3.11 portable + virtualenv with all backend deps preinstalled
  - Node.js 22 LTS portable + frontend production build (`.next/`)
  - NSSM service supervisor (auto-restart on crash, start on boot)
  - InsightFace `buffalo_l` ONNX models (~340 MB) optionally bundled
  - Backend + frontend registered as Windows Services
  - Desktop shortcut → `http://localhost:3000`

End user double-clicks `Setup.exe` → installer runs as Administrator →
copies files → migrates database → starts services → opens dashboard.
Total install time: ~2 minutes.

---

## Build prerequisites (on the BUILD machine, not the target)

| What | Where |
|---|---|
| **Inno Setup 6.2+** | https://jrsoftware.org/isdl.php |
| **PowerShell 5.1+** | already in Windows 10/11 |
| **Internet access** | for downloading Node.js + NSSM zips |
| **Backend venv** | run `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt` in `backend/` first |
| **Frontend build** | run `npm ci && npm run build` in `frontend/` first |

## Target machine prerequisites

| What | Why |
|---|---|
| **Windows 10/11 x64** | The installer is x64 only (matches InsightFace wheels). |
| **PostgreSQL 16** | **Bundled** — Setup.exe automatically installs PostgreSQL 16 silently on private port 55432 with an auto-generated password. No pre-installation required. |
| **Administrator privileges** | NSSM requires admin to register services. |
| **8 GB RAM minimum** | InsightFace `buffalo_l` loads ~500 MB into memory. |
| **(optional) Internet on first boot** | If InsightFace models aren't bundled (Section "Bundling models" below), they're downloaded on first run. |

## Build steps

```powershell
# 1. Stage all assets into deploy\installer\assets\ (5-10 min)
cd deploy\installer
.\stage-assets.ps1

# 2. Build the installer
# Open AICameraSurveillance.iss in Inno Setup Compiler
# Click Build → output is deploy\installer\output\AICameraSurveillance-Setup-1.0.0.exe
```

## End-user install

1. Right-click `Setup.exe` → **Run as administrator**.

2. Accept default install path (`C:\AICameraSurveillance`) or pick another.

3. Wait for "Setup complete." (~2 min — includes silent PostgreSQL 16 install on port 55432). Browser opens to `http://localhost:3000`.

4. Log in with `admin` / `ChangeMe@123`. System prompts to change the password.

5. Click **Detect on LAN** in the Cameras page — finds cameras automatically.

## Bundling InsightFace models (optional)

Without this, the FIRST boot takes 2-5 minutes downloading the buffalo_l
models. To pre-bundle them so install is fully offline:

```powershell
# Run on the build machine BEFORE stage-assets.ps1:
cd backend
.venv\Scripts\python.exe -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', root='./storage/models').prepare(ctx_id=-1)"
# This downloads + caches models under backend\storage\models\
# stage-assets.ps1 copies them automatically.
```

## Uninstall behavior

The uninstaller:

  - Stops + removes both services
  - Deletes the application directory
  - **Preserves `backend\storage\`** — biometric data + snapshots stay.
    The operator may need them for DPDP compliance / audit. Delete
    manually if you're disposing of the machine.

The Postgres database (`ai_attendance` table) is **not touched** by uninstall.
Drop it manually if you want a clean slate:

```cmd
"C:\Program Files\PostgreSQL\16\bin\dropdb.exe" -U postgres ai_attendance
```

## Troubleshooting the build

**"Backend venv not found"** — Run `python -m venv backend\.venv` first.

**".next not found"** — Run `npm run build` in `frontend/` first.

**"Node download failed"** — Check the `NodeUrl` parameter in `stage-assets.ps1`.
Versions on nodejs.org occasionally rotate.

**Inno Setup compiler complains about a path** — `assets/` must exist before
opening the .iss. Run `stage-assets.ps1` first.

## Troubleshooting the install

**"Service failed to start"** — Check `C:\AICameraSurveillance\logs\backend.log`.
Common causes: bundled Postgres service (`postgresql-x64-16` on port 55432) not
running, JWT secret not generated, antivirus quarantined a Python file.

**"http://localhost:3000 — refused to connect"** — Frontend service may have
crashed before binding. `net start AISurveillanceFrontend` to retry.

**"InsightFace model load failed"** — RAM exhausted. Close other apps;
required ~500 MB free.
