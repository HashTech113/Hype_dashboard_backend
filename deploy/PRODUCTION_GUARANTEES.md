# Production Deployment — What's Guaranteed to Work on Any Windows Box

This is a **full Setup.exe installer** — like a game or commercial app.
End-user double-clicks, clicks Next a few times, waits for the progress
bar, and launches the dashboard from the desktop. Zero command-line
steps, zero manual prerequisites.

---

## End-user install experience (what your customer sees)

1. **Download** `AICameraSurveillance-Setup-1.0.0.exe` (~900 MB)
2. **Right-click → Run as administrator** (UAC prompt)
3. Welcome screen → **Next**
4. License → **I accept** → **Next**
5. Install location (default `C:\AICameraSurveillance`) → **Next**
6. Desktop shortcut toggle → **Next**
7. **Install** button → progress bar runs ~3-5 minutes:
   - "Installing Visual C++ runtime..."
   - "Installing PostgreSQL (this is the slow step, ~90s)..."
   - "Configuring database connection..."
   - "Setting up application files..."
   - "Registering services..."
   - "Starting backend..."
   - "Starting frontend..."
8. **Finish** → dashboard opens in their default browser at `http://localhost:3000`
9. Login with `admin` / `ChangeMe@123` → forced password change → in.

That's it. No `createdb`, no `pip install`, no `npm install`, no `alembic upgrade`,
no `nssm set`, no firewall rule edits, no JWT secret generation.

---

## Hardware + OS requirements (operator must meet these)

| Requirement | Why |
|---|---|
| **Windows 10/11 x64** | The bundled wheels (InsightFace, OpenCV, ONNX Runtime) are x64-only. ARM is unsupported. |
| **8 GB RAM** | InsightFace `buffalo_l` loads ~500 MB on first detect call. With Postgres + Node + Python that's 1.5-2 GB resident. 8 GB is comfortable headroom. |
| **20 GB free disk** | Bundled installer (~900 MB), unpacked installation (~3 GB), 90 days of snapshots (~5 GB), Postgres data dir growth. |
| **Internet on first boot** *(unless models pre-bundled)* | InsightFace downloads ~340 MB of models from `insightface.ai` if `backend\storage\models\buffalo_l\` is missing. Air-gap option: bundle them via `stage-assets.ps1`. |
| **Administrator privileges** | Required for Windows Service registration + Postgres install. Only the install needs admin — runtime services run as `NetworkService`. |

---

## What's BUNDLED inside the Setup.exe (so end-user needs nothing)

| Bundled | Size | What it does |
|---|---|---|
| **PostgreSQL 16 installer** | ~250 MB | Silent-installed on a private port (55432) with an auto-generated password. End-user never sees Postgres. |
| **Visual C++ 2015-2022 redist** | ~25 MB | Required by OpenCV + ONNX wheels. Idempotent — skipped if already on the box. |
| **Portable Node.js 22 LTS** | ~30 MB | Frontend service runtime. Doesn't touch any system Node install. |
| **Backend venv** (Python 3.11 + all deps) | ~600 MB | InsightFace, OpenCV, FastAPI, SQLAlchemy, ONNX Runtime, everything. Snapshotted at build time. |
| **Frontend production build** (`.next/`) | ~60 MB | Pre-compiled Next.js bundle — zero compile time at runtime. |
| **NSSM** | ~330 KB | Windows Service supervisor. Handles auto-restart on crash. |
| **go2rtc** | ~6 MB | RTSP→WebRTC bridge. Bundled so first-boot is offline-capable. |
| *(optional)* **InsightFace models** | ~340 MB | Pre-bundled for air-gapped installs. By default downloaded on first detect call. |

Total Setup.exe size: **~900 MB without models, ~1.2 GB with models bundled**.

## How to build the Setup.exe

On the build machine (your dev box):

```cmd
deploy\build.cmd
```

That single command does everything:
1. Builds the Next.js production bundle
2. Downloads + stages Postgres, VC++, Node, NSSM, go2rtc
3. Runs Inno Setup Compiler → output `deploy\installer\output\Setup.exe`

Prerequisites on the **build machine** (not the target):
- Inno Setup 6 — https://jrsoftware.org/isdl.php
- Backend venv created (`python -m venv backend\.venv && backend\.venv\Scripts\pip install -r backend\requirements.txt`)
- Node 20+ installed

First build: ~15 minutes (downloads + venv copy + npm build). Subsequent builds: ~3 minutes.

---

## What the installer guarantees automatically

These are concerns the operator should NEVER have to think about. They're
handled by code that runs on first boot or by the installer itself.

### 1. JWT secret auto-generates on first boot

The `.env` file shipped with the installer has `JWT_SECRET_KEY` left empty.
On first uvicorn start, [`app/config.py`](../backend/app/config.py)'s
`_auto_jwt_secret` validator notices the empty value, generates a 48-byte
URL-safe secret, and writes it back to `.env`. Subsequent boots read the
persisted secret.

**Without this**: fresh install crashes on startup with `JWT_SECRET_KEY
Field required` — the most common production-deploy footgun.

### 2. Database auto-creates if missing

If the operator's Postgres has no `ai_attendance` database,
[`app/db/session.py`](../backend/app/db/session.py)'s `_ensure_database_exists`
connects to the `postgres` admin DB, checks for our target, and `CREATE
DATABASE`s it.

**Without this**: operator had to `createdb ai_attendance` manually
before first boot.

### 3. Alembic migrations auto-run on every boot

[`app/main.py`](../backend/app/main.py)'s `_auto_migrate` runs `alembic
upgrade head` inside the lifespan startup hook. This means:
- First boot: tables are created
- Upgrade: pulling a newer code version auto-migrates the schema
- Restore from backup: missing migrations re-apply

**Failures are logged but DO NOT block startup** — the app boots so the
operator can see the health dashboard pointing to the schema problem.

### 4. Storage paths are CWD-independent

All `./storage/...` paths in `.env` are anchored to the **backend
directory** (where `app/` lives), not the launcher's CWD. So:
- Running via NSSM service → works
- Running via `python -m uvicorn` from anywhere → works
- Running via Windows Task Scheduler → works
- Operator copies the entire install folder to D:\ → works

Absolute paths like `D:\ai-storage` are passed through unchanged, so the
operator can move large data to a separate drive without code changes.

### 5. CORS auto-allows LAN access

The CORS middleware allows any origin matching:
- `http://localhost` or `http://127.0.0.1` (any port)
- `http://10.x.x.x:*` (private class A)
- `http://192.168.x.x:*` (private class C)
- `http://172.16-31.x.x:*` (private class B)

So accessing the dashboard from a tablet on the same LAN works without
configuration. The operator can override with explicit
`CORS_ALLOW_ORIGINS=https://attendance.company.com,https://admin.company.com`
in `.env` for production hostnames.

### 6. Bootstrap admin seeds itself

On first boot, if the `admins` table is empty,
[`app/services/auth_service.py`](../backend/app/services/auth_service.py)'s
`bootstrap_admin` creates `admin` / `ChangeMe@123` as `SUPER_ADMIN`. The
log emits a `WARNING` reminding the operator to change the password.

### 7. go2rtc downloads itself on first boot (if not bundled)

If `backend\storage\bin\go2rtc.exe` is missing,
[`app/services/go2rtc_service.py`](../backend/app/services/go2rtc_service.py)
auto-downloads from the official GitHub release (~6 MB). If no internet,
WebRTC silently falls back to the WebSocket JPEG stream — the live view
still works.

### 8. InsightFace models download themselves on first boot

If `backend\storage\models\buffalo_l\` is missing, the first call to
`FaceAnalysis(...)` downloads ~340 MB from `insightface.ai`. If no
internet, app crashes with a clear error. **For air-gapped installs**,
bundle the models in `stage-assets.ps1` before building Setup.exe (see
[`installer/README.md`](installer/README.md)).

### 9. Camera streaming is self-healing

- **RTSP buffer overflow** → drain thread always reads the latest frame,
  never accumulates lag. Fixed in
  [`backend/app/workers/rtsp_reader.py`](../backend/app/workers/rtsp_reader.py).
- **Worker crash** → CameraManager auto-restarts via the health loop.
- **Camera disconnect** → exponential backoff reconnect, max 30s.
- **FFmpeg buffer init** → low-latency flags set at module load time.

---

## Smoke test after install

Always run [`deploy/runtime/verify-install.ps1`](runtime/verify-install.ps1)
after install. It checks:

1. **File-system layout** — backend, frontend, venv, bundled tools present
2. **PostgreSQL** — service running + listening on 5432
3. **Backend** — /health 200, /health/ready 200, DB OK, model loaded
4. **go2rtc** — bridge responsive (warns if down — not critical)
5. **Frontend** — /login serves HTML, has API URL configured
6. **End-to-end** — admin login returns a valid JWT

Exit code 0 = production-ready. Exit code 1 = one or more critical
checks failed; the script tells the operator which and where to look.

---

## What CAN still go wrong + the fix

| Symptom | Likely cause | Operator action |
|---|---|---|
| `/health/ready` reports DB error | Postgres service stopped | `net start postgresql-x64-16` |
| `/health/ready` reports model not loaded | First-boot model download interrupted | Restart the backend service; it retries the download |
| Live view shows "Camera disabled" everywhere | All cameras inactive in DB | Use Cameras page → Smart Connect to re-add |
| Live view shows "Stream unavailable" | RTSP URL or creds wrong | Use Edit → fix URL/password → Restart worker |
| Smart Connect shows "request timed out" | Wrong port (8000 instead of 554) | Wizard auto-corrects to 554 if it's open; otherwise verify camera IP is reachable |
| Browser shows blank page | Frontend service crashed | `net start AISurveillanceFrontend` |
| "CORS error" in browser console | Operator typed a custom hostname | Add the hostname to `CORS_ALLOW_ORIGINS` in `.env` |
| Auto-discovery finds 0 cameras | Cameras have ONVIF disabled | TCP scan fallback should find them; also check Windows Firewall outbound UDP 3702 |

---

## Production-grade defaults

These ship pre-configured for production:

| Setting | Production value | Why |
|---|---|---|
| `APP_DEBUG` | `false` | No stack traces in API responses |
| `LOG_LEVEL` | `INFO` | Enough signal, not too much noise |
| `LOG_MAX_BYTES` | 100 MB | Rotation prevents log dir from filling disk |
| `LOG_BACKUP_COUNT` | 5 | 500 MB max log retention |
| uvicorn `--no-access-log` | enabled | Per-request log is too noisy + adds 1-3 ms latency |
| uvicorn `--workers 1` | single worker | InsightFace's 500 MB footprint × N workers = OOM. Detection is GIL-released so one worker handles many cameras fine. |
| NSSM `AppExit Default Restart` | restart on crash | Five-second throttle prevents tight crash loops |
| NSSM `AppRotateBytes 100MB` | log rotation | Self-managing logs even if our Python rotation fails |
| `pool_pre_ping=True` | DB connection healthcheck | Stale connection after DB restart auto-recovers |
| `pool_recycle=1800` | 30-min connection refresh | Avoids long-running idle connections being killed by intermediate proxies |

---

## Final acceptance test

```powershell
# 1. Run the smoke test
cd C:\AICameraSurveillance\deploy\runtime
.\verify-install.ps1

# Expected output:
#   ALL CRITICAL CHECKS PASSED
#   Open http://localhost:3000 in your browser.

# 2. Open the dashboard, log in with admin / ChangeMe@123, change the password.

# 3. Add a camera via Smart Connect — IP, username, password, name. Save.

# 4. Verify the live tile shows the camera streaming within ~5 seconds.

# 5. Add 1-2 employees with face photos via Face Training.

# 6. Walk in front of the camera. Verify the live tile draws a green box
#    with the employee's name + match %.

# 7. Verify the Activity Log records an entry event with timestamp + camera.
```

If all 7 steps pass on a freshly-installed machine, the installer is
production-ready.
