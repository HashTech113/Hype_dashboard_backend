# AI CCTV Attendance — Production Deployment Runbook

Single-site, single-PC, Windows 10/11 deployment. Designed to run for years
without manual intervention.

This document covers the **complete** lifecycle: install → configure →
monitor → backup → upgrade → recover. Every P0 from the audit is resolved
by following this runbook end-to-end.

---

## Table of contents

1. [Hardware & OS prerequisites](#1-hardware--os-prerequisites)
2. [Software prerequisites](#2-software-prerequisites)
3. [Network setup](#3-network-setup)
4. [Initial install](#4-initial-install)
5. [Security hardening](#5-security-hardening)
6. [Install as Windows Services (NSSM)](#6-install-as-windows-services-nssm)
7. [TLS reverse proxy (Caddy)](#7-tls-reverse-proxy-caddy)
8. [Automated backups](#8-automated-backups)
9. [Monitoring & alerts](#9-monitoring--alerts)
10. [Day-to-day operations](#10-day-to-day-operations)
11. [Upgrades](#11-upgrades)
12. [Disaster recovery](#12-disaster-recovery)
13. [Compliance (India DPDP Act 2023)](#13-compliance-india-dpdp-act-2023)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Hardware & OS prerequisites

| Item | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores, AVX2 | 8 cores, AVX2 |
| RAM | 8 GB | 16 GB |
| SSD | 256 GB | 512 GB (encrypted with BitLocker) |
| OS | Windows 10 Pro / 11 Pro | Windows 11 Pro 24H2 |
| GPU | Not required | NVIDIA + CUDA (optional 3-5× speedup) |

**BitLocker** must be enabled on the system drive — biometric data is
sensitive PII under DPDP. Without disk encryption, a stolen SSD leaks
every face template + every attendance record.

To enable BitLocker:
```cmd
manage-bde -on C: -RecoveryPassword
```
Save the recovery key to a sealed envelope in physical storage offsite.

---

## 2. Software prerequisites

Install each in this order — each is a one-time setup:

| Software | Where | Purpose |
|---|---|---|
| **PostgreSQL 16** | https://www.postgresql.org/download/windows/ | Database. Install as a Windows Service (default). |
| **Python 3.11** | https://www.python.org/downloads/ | Backend runtime. Check "Add to PATH". |
| **Node.js 22 LTS** | https://nodejs.org | Frontend build + runtime. |
| **Git for Windows** | https://git-scm.com/download/win | Source code + upgrades. |
| **NSSM 2.24+** | https://nssm.cc/download | Windows Service supervisor. Extract to `C:\nssm\`. |
| **Caddy 2.x** | https://caddyserver.com/download | TLS reverse proxy. Extract to `C:\caddy\`. |
| **7-Zip** | https://7-zip.org | AES-256 backup encryption. |

After installing, reboot or open a fresh terminal so the PATH is updated.

---

## 3. Network setup

The AI PC must be on the camera network.

### Option A — Camera switch directly to AI PC (single-port, simplest)

1. Plug the PoE switch's uplink Ethernet into the AI PC's LAN port.
2. Set a static IP on the LAN adapter:
   - IP: `192.168.1.50`
   - Subnet mask: `255.255.255.0`
   - Gateway: leave blank (cameras don't need internet)
3. Verify with `ping 192.168.1.201` (or whatever camera IP).

### Option B — Office Wi-Fi + camera LAN (recommended)

1. Use the Wi-Fi adapter for office network / internet.
2. Use the LAN adapter for cameras (192.168.1.x).
3. Both can coexist — Windows routes by destination.

### Open Windows Firewall ports

| Port | Service |
|---|---|
| 443 | Caddy HTTPS — admin access from office LAN |
| 80  | Caddy HTTP → HTTPS redirect |

The backend (8000) and frontend (3000) bind to `127.0.0.1` only and don't
need firewall rules.

```cmd
netsh advfirewall firewall add rule name="AI Attendance HTTPS" dir=in action=allow protocol=TCP localport=443
netsh advfirewall firewall add rule name="AI Attendance HTTP" dir=in action=allow protocol=TCP localport=80
```

---

## 4. Initial install

### 4a. Clone

```cmd
cd "C:\Users\<USERNAME>\OneDrive\Desktop"
git clone https://github.com/HashTech113/ai-camera-attendance-system.git "ai cameera attendance"
cd "ai cameera attendance"
```

### 4b. Backend setup

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4c. Generate JWT secret & populate `.env`

```cmd
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output. Then create `backend\.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/ai_attendance
JWT_SECRET_KEY=<PASTE THE 48-CHAR SECRET HERE>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=Temp@123-Change-Immediately
FACE_MODEL_NAME=buffalo_l
FACE_MODEL_ROOT=./storage/models
FACE_PROVIDER=CPUExecutionProvider
FACE_DET_SIZE=320
FACE_MATCH_THRESHOLD=0.45
FACE_MIN_QUALITY=0.50
FACE_TRAIN_MIN_IMAGES=5
FACE_TRAIN_MAX_IMAGES=20
CAMERA_FPS=1
CAMERA_COOLDOWN_SECONDS=5
CAMERA_HEALTH_INTERVAL_SECONDS=10
CAMERA_HEARTBEAT_TIMEOUT_SECONDS=30
RTSP_CONNECT_TIMEOUT_MS=5000
RTSP_READ_TIMEOUT_MS=5000
RTSP_RECONNECT_MAX_SECONDS=30
STORAGE_ROOT=./storage
TRAINING_DIR=./storage/training_images
SNAPSHOT_DIR=./storage/snapshots
UNKNOWNS_DIR=./storage/unknowns
TIMEZONE=Asia/Kolkata
CORS_ALLOW_ORIGINS=["https://attendance.local"]
LOG_LEVEL=INFO
LOG_DIR=./logs
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=5
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_BASE_SECONDS=60
LOGIN_LOCKOUT_MAX_SECONDS=3600
```

**Important:**
- `JWT_SECRET_KEY` is validated at startup. If it's blank, < 32 chars, or
  starts with `dev-local-secret`, `change-me`, etc., the backend **refuses
  to start**. This is intentional — see P0.5.
- `BOOTSTRAP_ADMIN_PASSWORD` only seeds the FIRST admin. After login the
  operator is **forced** to change it.

### 4d. Database setup

```cmd
"C:\Program Files\PostgreSQL\16\bin\createdb.exe" -U postgres ai_attendance
.venv\Scripts\python.exe -m alembic upgrade head
```

### 4e. Download face models

The first time uvicorn starts, InsightFace downloads `buffalo_l` (~300 MB)
to `./storage/models`. Needs internet on first run. After that, fully
offline.

### 4f. Frontend setup

```cmd
cd ..\frontend
npm install --include=dev
echo NEXT_PUBLIC_API_URL=/api/v1 > .env.local
npm run build
```

The `NEXT_PUBLIC_API_URL=/api/v1` (relative) is critical — when Caddy is
in front, both frontend and backend share the same origin.

### 4g. First-boot smoke test

```cmd
cd ..\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

In another terminal:
```cmd
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

You should see `{"status":"ok"}` and a JSON report with all checks `"ok": true`.

If ready returns 503, see the JSON body for which check is failing.

---

## 5. Security hardening

| Control | How it's enforced |
|---|---|
| Password hashing | bcrypt (12 rounds) for stored passwords. |
| Stateless auth | JWT (HS256). Set a strong `JWT_SECRET_KEY` (48-char random); the system does not enforce strength, so the operator must generate one — see Section 4c. |
| HTTPS-only | Caddy in front; HSTS header sent. |
| RBAC | SUPER_ADMIN required for: admin mgmt, biometric erasure, day-reopen, snapshot purge, camera delete. |
| Single-point-of-lockout safe | Admin endpoint refuses to remove / demote the last active SUPER_ADMIN. |
| Erasure confirmation | Right-to-erasure requires confirmation phrase `ERASE <employee_code>`. |
| Audit log (non-login) | Every admin create/update + biometric erasure + password change logged to `admin_audit_log`. Login events are NOT logged (intentional — single-operator office on private LAN). |

**Removed at operator request** (still possible to add back later):
  - Brute-force lockout — login accepts unlimited attempts; rate-limit at the network layer (Caddy) if needed.
  - Force-password-change on first login — change is voluntary via `/change-password`.
  - JWT secret strength validator — operator is responsible for generating a strong secret at install (see Section 4c).
  - Login audit log entries — `LOGIN_SUCCESS` / `LOGIN_FAILED` rows are no longer written.

---

## 6. Install as Windows Services (NSSM)

This is **P0.1** — the single highest-impact fix. Without it the system
dies the moment uvicorn's terminal is closed.

```cmd
cd "C:\Users\<USERNAME>\OneDrive\Desktop\ai cameera attendance\deploy"
powershell -ExecutionPolicy Bypass -File .\install-services.ps1
```

The script:
1. Validates prerequisites (NSSM, venv, .next/ build present).
2. Creates `AISurveillanceBackend` and `AISurveillanceFrontend` Windows Services.
3. Sets both to auto-start on boot.
4. Sets auto-restart on crash (5s delay).
5. Sets log rotation (100 MB × multiple files).
6. Makes frontend depend on backend so it starts second.

After install:
```cmd
Get-Service AISurveillance*
```
Both should show `Status: Running, StartType: Automatic`.

Stop / restart later:
```cmd
nssm stop AISurveillanceBackend
nssm start AISurveillanceBackend
```

---

## 7. TLS reverse proxy (Caddy)

This is **P0.8** — without it, every JWT and every face image travels in
plain text on the LAN.

1. Copy `deploy\Caddyfile` to `C:\caddy\Caddyfile`.
2. Add to `C:\Windows\System32\drivers\etc\hosts`:
   ```
   192.168.1.50  attendance.local
   ```
   (Adjust `192.168.1.50` to your AI PC's actual LAN IP.)
3. Install Caddy as a Windows Service:
   ```cmd
   nssm install Caddy C:\caddy\caddy.exe run --config C:\caddy\Caddyfile
   nssm set Caddy Start SERVICE_AUTO_START
   nssm set Caddy AppDirectory C:\caddy
   nssm set Caddy AppExit Default Restart
   nssm start Caddy
   ```
4. Verify: open https://attendance.local in a browser. First time, the
   browser warns about the self-signed cert — accept it. Future visits
   are clean (HSTS pinned for 1 year).

For a public domain (rare for an office system): replace `attendance.local`
in the `Caddyfile` with your real domain. Caddy auto-fetches a
Let's Encrypt cert — the machine must be reachable on ports 80 + 443.

---

## 8. Automated backups

This is **P0.2**. Without it, an SSD failure means total loss.

### Set a backup password

Pick a strong one. Store offsite (sealed envelope / password vault).

### Schedule the backup task

Run **once** as Administrator:

```cmd
schtasks /Create /SC DAILY /TN "AIAttendanceBackup" ^
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\<USERNAME>\OneDrive\Desktop\ai cameera attendance\deploy\backup.ps1 -EncryptionPassword <YOUR-PASSWORD> -BackupTarget \\NAS\backups\ai-attendance" ^
  /ST 02:00 /RL HIGHEST /F
```

Adjust:
- `\\NAS\backups\ai-attendance` → wherever your offsite/secondary storage lives.
- `<YOUR-PASSWORD>` → the 7-Zip AES-256 password.

### Verify

After 2 AM the next day, check `\\NAS\backups\ai-attendance\`:
- One `.7z` file per day
- `backup.log` with INFO entries

### Restore drill (do this once now, then every 6 months)

```cmd
# 1. Decrypt
7z x ai-attendance-20260608-020000.dump.7z -pPASSWORD
# 2. Restore to a TEST database (not production!)
"C:\Program Files\PostgreSQL\16\bin\createdb.exe" -U postgres ai_attendance_restore_test
"C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" -U postgres -d ai_attendance_restore_test ai-attendance-20260608-020000.dump
# 3. Inspect — make sure tables exist, rows are present
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d ai_attendance_restore_test -c "SELECT COUNT(*) FROM attendance_events"
# 4. Drop the test DB
"C:\Program Files\PostgreSQL\16\bin\dropdb.exe" -U postgres ai_attendance_restore_test
```

**Untested backups are not backups.** Do the restore drill twice a year
minimum.

---

## 9. Monitoring & alerts

### Built-in endpoints

| Endpoint | What it returns |
|---|---|
| `GET /health` | 200 if HTTP server is up. Used by Caddy / NSSM. |
| `GET /health/ready` | 200 if everything healthy, 503 if anything critical down. JSON body lists each subsystem. |
| `GET /health/disk` | Disk usage report — surfaced in the dashboard. State: OK / WARN / CRITICAL. |

### Dashboard widgets

The Cameras page shows per-worker `health_state` (CONNECTING / STREAMING /
FLAPPING / DEGRADED) + reconnect counts + last error.

### Suggested external monitor

Point a simple uptime tool (UptimeRobot, Better Uptime, etc.) at
`https://attendance.local/health/ready`. Set alert threshold = 2 consecutive
failures over 10 minutes.

### Disk-space alert (Windows scheduled task)

Add a daily check that emails the operator if free space < 10%:

```powershell
$free = (Get-PSDrive C).Free / 1GB
if ($free -lt 25) {
    Send-MailMessage -To "ops@example.com" -From "no-reply@example.com" `
      -Subject "AI Attendance: low disk space ($free GB)" `
      -Body "C: has only $free GB free. Clear logs or expand storage." `
      -SmtpServer "smtp.example.com"
}
```

---

## 10. Day-to-day operations

### Add an employee
1. Cameras page → ensure all are LIVE.
2. Employees → New → fill the form.
3. Training → select the employee → upload 5-20 face images OR capture
   from a camera.
4. Consent record gets created automatically.

### Add a camera
1. Cameras → Smart Connect.
2. Enter IP + username + password. The wizard auto-discovers via ONVIF.
3. Set ENTRY / EXIT + optional per-camera FPS.

### Add a second admin
1. Log in as the existing SUPER_ADMIN.
2. `POST /api/v1/admins` (via Swagger or future UI):
   ```json
   { "username": "operator", "full_name": "Office Manager", "role": "ADMIN",
     "initial_password": "Temp@2026-Change", "must_change_password": true }
   ```
3. Operator logs in with the temp password, is forced to rotate.

### Forgot password (operator side)
1. SUPER_ADMIN resets it: `PATCH /api/v1/admins/{id}` with `{ "reset_password": "NewTemp" }`.
2. Target admin logs in with the new password and rotates via `/change-password` when convenient.

### Employee leaves — right-to-erasure
1. SUPER_ADMIN: `POST /api/v1/erasure/employee/{id}` with:
   ```json
   { "confirmation_phrase": "ERASE <employee_code>",
     "reason": "Employee resignation",
     "delete_employee_row": false,
     "anonymize_attendance_events": true }
   ```
2. Audit row written to `biometric_purge_log`. Embedding cache reloads.

---

## 11. Upgrades

```cmd
cd "C:\Users\<USERNAME>\OneDrive\Desktop\ai cameera attendance"
git fetch
git log HEAD..origin/main --oneline  # review what's changing
git pull

# Stop services to avoid file-lock errors during install/build
nssm stop AISurveillanceFrontend
nssm stop AISurveillanceBackend

# Backend
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
.venv\Scripts\python.exe -m alembic upgrade head

# Frontend
cd ..\frontend
npm install
npm run build

# Restart
cd ..
nssm start AISurveillanceBackend
nssm start AISurveillanceFrontend

# Verify
curl http://127.0.0.1:8000/health/ready
```

If anything's wrong after upgrade, roll back: `git checkout <prev-sha>`
and repeat. The DB migration's `downgrade()` undoes the schema change.

---

## 12. Disaster recovery

### Drive failure / total loss

Time-to-recovery target: **2-4 hours** with offsite backups.

1. Install Windows + prerequisites on the new drive / PC (Section 2).
2. Clone the repo (Section 4a-c). Use the **same `JWT_SECRET_KEY`** if
   you want existing sessions to keep working; otherwise generate a new
   one and admins re-login.
3. Restore the latest backup:
   ```cmd
   7z x ai-attendance-LATEST.dump.7z -pPASSWORD
   "C:\Program Files\PostgreSQL\16\bin\createdb.exe" -U postgres ai_attendance
   "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" -U postgres -d ai_attendance LATEST.dump
   ```
4. Storage / face images: re-copy from `\\NAS\backups\storage\` if you
   were mirroring it, OR re-train employees (they'll need to upload
   photos again — labour-intensive but fully recoverable).
5. Re-install services (Section 6). Re-install Caddy (Section 7).
6. Reschedule the backup task (Section 8).

### Bootstrap admin password lost AND only one admin exists

The bootstrap password from the original `.env` cannot be recovered. To
get back in:

1. Connect to Postgres directly:
   ```cmd
   "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d ai_attendance
   ```
2. Generate a bcrypt hash:
   ```cmd
   .venv\Scripts\python.exe -c "from passlib.hash import bcrypt; print(bcrypt.hash('NewTemp@123'))"
   ```
3. Update the admin row:
   ```sql
   UPDATE admins
   SET password_hash = '<paste-the-hash>'
   WHERE username = 'admin';
   ```
4. Log in with `NewTemp@123` and rotate via `/change-password` when convenient.

---

## 13. Compliance (India DPDP Act 2023)

The system processes biometric data — under DPDP Sec 2(t) this is "personal
data" and Sec 7 requires explicit consent + Sec 8(7) requires purpose-bound
retention + Sec 12 requires right-to-erasure.

### What the system does for you

| Requirement | How it's met |
|---|---|
| Explicit consent (Sec 6) | `consent_records` table; create one per employee per scope before training. |
| Right to access (Sec 11) | `GET /api/v1/employees/{id}`, `GET /api/v1/attendance/daily/employee/{id}`, snapshot files. Export to xlsx via reports. |
| Right to erasure (Sec 12) | `POST /api/v1/erasure/employee/{id}` — deletes embeddings, images, snapshots; writes immutable audit row. |
| Audit trail (Sec 8 / 21) | `admin_audit_log` table — every login, role change, erasure. Never deleted. |
| Encryption at rest | BitLocker on system drive (Section 1) + 7-Zip AES-256 on backups (Section 8). |
| Encryption in transit | Caddy TLS + HSTS (Section 7). |
| Breach notification (Sec 8(6)) | Operator runbook below. |

### Breach notification runbook

Under DPDP, the Data Protection Board must be notified "as soon as
possible" of a personal-data breach. Targeted timeline: within 24 hours.

1. Identify scope (which employees? which data classes? when did the
   exposure start / stop?). Use `admin_audit_log` to reconstruct.
2. Contain (rotate JWT secret, change all admin passwords, isolate
   network, revoke any leaked keys).
3. Notify the Data Protection Board via the official portal.
4. Notify affected data principals with the same information.

### Consent capture during training

Use the new endpoint:
```http
POST /api/v1/consent
{
  "employee_id": 42,
  "scope": "BIOMETRIC_CAPTURE",
  "consent_text": "I, <name>, consent to my face being recorded and used for office attendance under the AI CCTV Attendance system, in line with the company's DPDP-aligned privacy notice dated YYYY-MM-DD. I understand I may withdraw this consent at any time."
}
```

The text should match the consent letter the employee physically signed.
Keep the signed copy in the HR file.

### Withdraw consent + purge

```http
POST /api/v1/consent/{id}/withdraw
POST /api/v1/erasure/employee/{employee_id}
```

### Uninstall — storage retention is the operator's responsibility

`deploy\runtime\uninstall-services.cmd` stops and removes the two Windows
Services, then explicitly prompts:

> Do you want to DELETE biometric data and snapshots now? (Y/n)

- Answering **Y** purges `backend\storage\training_images`, `snapshots`,
  `unknowns`, `embeddings`, and `previews`. The `audit` subdirectory (if
  present) is copied to `dpdp_audit_preserved\` first, because audit rows
  must survive per Sec 8 / 21.
- Answering **n** (or pressing Enter) leaves `backend\storage` in place. In
  that case **the operator is legally responsible** for deleting or securely
  archiving the directory to remain compliant with DPDP Act 2023 Section
  8(7) (purpose-bound retention).

Every uninstall run appends a line to `dpdp_uninstall_audit.log` at the
repo root recording the decision (PURGED vs RETAINED), operator username,
host, and timestamp. Keep this file with your DPDP compliance records.

The PostgreSQL database (`ai_attendance`) is **not** touched by the
uninstall script. Drop it manually with `dropdb ai_attendance` after the
uninstall if you want a full purge of employee records, embeddings, and
audit history.

---

## 14. Troubleshooting

### Frontend shows "Loading your session…" forever

1. Check the backend is up: `curl http://127.0.0.1:8000/health`.
2. Check Caddy is up: `Get-Service Caddy`.
3. Open browser DevTools → Network tab — what does `/api/v1/auth/me` return?

### Browser shows "Network Error" on login (dev mode)

Three things to check in order:

1. **Frontend `.env.local`** must use **`127.0.0.1`**, not `localhost`:
   ```
   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
   ```
   `NEXT_PUBLIC_*` env vars are baked in at compile time — restart
   `next dev` after editing.

2. **Watch out for a polluted system-level `NEXT_PUBLIC_API_URL`** (e.g.
   from an unrelated project on the same machine). Windows User env vars
   take precedence over `.env.local` by default. As of this fix,
   `next.config.mjs` reloads `.env.local` and overrides any polluted
   shell value at startup — look for this line in the dev log:
   ```
   [next.config] Overrode polluted env var NEXT_PUBLIC_API_URL: was "X" -> using "Y" from .env.local
   ```

3. **Hard-refresh the browser tab** (Ctrl+Shift+R) — the bundle is cached
   client-side and a stale build still has the old URL.

### Stuck on "Loading your session…" after login

After ~6 seconds the page now shows an actionable error with a Sign-out
button. The two common causes:

1. **Browser cached an old JS bundle** pointing at the wrong backend.
   Click "Hard reload" on the stuck-state page (or Ctrl+Shift+R).
2. **You browsed via mixed hostnames** (e.g. logged in via
   `localhost:3000`, then opened `127.0.0.1:3000` in a different tab).
   The auth cookie is scoped per hostname — they're treated as separate
   origins. **In dev, pick one hostname and use it consistently.**

### IMPORTANT — dev-mode hostname rule

In `next dev` mode, Next.js silently rewrites redirect Location headers
to its canonical hostname (`localhost`) even when you browse via
`127.0.0.1`. This causes cookie-scope splits and login loops.

**Rule for dev: use `http://localhost:3000` everywhere.** Bookmark it,
type it, don't accept Chrome's autocomplete to `127.0.0.1`.

In production behind Caddy at `https://attendance.local`, the redirect
hostname is honored correctly and there's no issue.

### Camera shows "Degraded"

Reader has had 10+ consecutive open failures. Possible causes:
- Camera power off / Ethernet unplugged
- Camera IP changed
- Camera password rotated
- Camera firmware upgrade changed RTSP path

Try: Edit camera → "Test" button. Or remove + re-add via Smart Connect.

### Disk space WARN

`/health/disk` shows breakdown. Usually it's snapshots — purge old ones
via `DELETE /api/v1/snapshots/purge?before=YYYY-MM-DD`.

### Backup fails with "pg_dump exited with code N"

- Code 2 → connection failed. Check Postgres service is running.
- Code 1 → permission denied. Check `PGPASSWORD` env is set in the
  scheduled-task command line.

### Power loss mid-write

Postgres journals everything; the next start replays. No action needed.
File writes (snapshots) use Postgres-tracked references — if a file is
missing on disk but referenced in the DB, the snapshot view simply shows
"No image" for that event.

---

## Appendix — Files this runbook references

```
ai cameera attendance/
├── DEPLOYMENT.md          # this file
├── PRODUCTION_AUDIT_PUNCHLIST.md  # full audit findings
├── backend/
│   ├── .env               # secrets — never commit
│   ├── alembic.ini
│   └── ...
├── frontend/
│   └── ...
└── deploy/
    ├── install-services.ps1  # NSSM service installer (P0.1)
    ├── backup.ps1            # pg_dump + 7z encrypt + rotate (P0.2)
    └── Caddyfile             # TLS reverse proxy (P0.8)
```

---

**End of runbook.** If you ever need to re-derive this, run
`PRODUCTION_AUDIT_PUNCHLIST.md` again — every section here corresponds to
one or more P0 items in that audit.
