# Production-readiness audit punchlist

**Total verified findings:** 135 (P0=21, P1=70, P2=44)


## P0_CRITICAL (21 items) — ship-blockers

### P0.1 [DEPLOYMENT_OPS] No disk-space monitoring or low-space alerting
- **File:** `backend/app/api/v1/snapshots.py:storage_stats L42-54`
- **Issue:** `storage_stats` reports `total_bytes` but never compares against free disk. Snapshots accumulate at ~1 image per recognition; unknowns grow until 5000 cap; logs grow to 500 MB; Postgres data dir grows. Nothing watches `shutil.disk_usage` on STORAGE_ROOT / log dir / PG data drive and warns the admin before the OS hits 100% full.
- **Impact:** When disk fills, snapshot writes fail (caught and logged), Postgres refuses writes (attendance stops being recorded — silent data loss for live events), and log rotation thrashes. The operator only finds out when a user reports 'attendance not working today'. Recoverable but expensive incident.
- **Fix:** Add a periodic disk-space probe (every 60s) that records free bytes on STORAGE_ROOT, LOG_DIR, and the PG drive. Surface a `low_disk_warning` field in `/health/ready` and the dashboard, with configurable thresholds (default 10% free / 5GB). Optionally email/log a P1 when crossed.
- **Effort:** SMALL

### P0.2 [DEPLOYMENT_OPS] No automated DB backup — single PG, no replica
- **File:** `DEPLOYMENT:no backup script, no doc, no scheduled task`
- **Issue:** Per deployment notes there is no PG replica, no scheduled `pg_dump`, no documented restore runbook. Years of attendance + biometric embeddings live on a single Windows 10 PC's drive. The settings table is also the only place threshold and office-hours config exists.
- **Impact:** Disk failure or ransomware = total loss of attendance history and trained employee embeddings (employees must re-train, weeks of work). Under DPDP 2023, biometric data is sensitive personal data with retention/integrity obligations; total loss is also a compliance breach.
- **Fix:** Ship a `scripts/backup.ps1` that runs `pg_dump --format=custom`, compresses, writes to a separate drive or network share with a date stamp, retains 30 days, and logs a `job_run` row. Register as Windows Task Scheduler nightly. Document restore procedure in README. Also back up `./storage/training_images` (embeddings can be regenerated from these).
- **Effort:** MEDIUM

### P0.3 [DEPLOYMENT_OPS] uvicorn run as foreground process — no supervisor, no auto-restart
- **File:** `DEPLOYMENT:no NSSM/Windows Service/systemd configuration`
- **Issue:** Per deployment context there is no process supervisor. If uvicorn dies (unhandled exception in lifespan, OOM, antivirus kill), it stays dead until someone double-clicks a batch file. Survives OS reboot only if there is a startup shortcut — and that runs as user, not as a service, so a logout kills it.
- **Impact:** Power outage at 2 AM = attendance offline at 9 AM. Any unhandled crash = system down until manual intervention. This is the single largest threat to 'runs for YEARS without a single error'.
- **Fix:** Install via NSSM (Non-Sucking Service Manager) as a Windows Service, with auto-restart on crash and start-on-boot. Document in DEPLOYMENT.md. Same for PostgreSQL (verify it is installed as a service, not interactive). Add stdout/stderr redirection to log dir.
- **Effort:** SMALL

### P0.4 [SECURITY] No JWT_SECRET_KEY strength validation; dev secret accepted silently
- **File:** `backend/app/config.py:lines 27-29; no validator`
- **Issue:** JWT_SECRET_KEY is loaded as a bare `str` with no minimum-length check, no entropy check, and no rejection of the known dev string `dev-local-secret-change-me-...`. The current .env ships that exact dev secret and the app boots fine. With HS256 a short/known secret means any attacker who knows it (or can crack it offline from a single captured token) can forge SUPER_ADMIN tokens and own the whole biometric DB.
- **Impact:** Anyone who reads the repo's example secret or who scrapes a forgotten dev .env file can mint valid SUPER_ADMIN JWTs against any deployment that wasn't manually re-keyed. Over years of production this WILL happen at least once (handover, leaked screenshot, abandoned VM).
- **Fix:** Add a Pydantic `field_validator` on `JWT_SECRET_KEY` that (a) rejects the literal `dev-local-secret-change-me-...` prefix and any string < 32 chars, and (b) refuses to start unless the value has reasonable entropy. Log a P0 boot-time error and `sys.exit(1)` if violated. Provide a `python -c "import secrets;print(secrets.token_urlsafe(48))"` one-liner in the README for the operator.
- **Effort:** SMALL

### P0.5 [SECURITY] Bootstrap admin password ChangeMe@123 is never force-rotated
- **File:** `backend/app/services/auth_service.py:bootstrap_admin() lines 70-86; Admin model has no must_change_password flag`
- **Issue:** `bootstrap_admin()` seeds the initial SUPER_ADMIN with BOOTSTRAP_ADMIN_PASSWORD (defaults to `ChangeMe@123`) and only emits a `log.warning(... change the password immediately)`. Nothing in the API, login flow, or DB model enforces that the operator actually changes it. The `Admin` model has no `must_change_password` / `password_changed_at` column, and `/auth/login` accepts the default forever.
- **Impact:** In an Indian office deployment with several IT handovers per year, default `admin / ChangeMe@123` will remain valid on a non-trivial fraction of installs. Anyone on the LAN with access to port 8000 (no HTTPS) can log in as SUPER_ADMIN and export every employee's face biometric.
- **Fix:** Add `password_changed_at: datetime` and `must_change_password: bool` columns to `admins`. Seed the bootstrap admin with `must_change_password=True`. In `AuthService.authenticate` set a flag on the returned token (or 200-with-`password_change_required: true`) and reject every non-`/auth/change-password` request from that user until they rotate. Refuse to bootstrap at all if `BOOTSTRAP_ADMIN_PASSWORD == 'ChangeMe@123'` and APP_DEBUG is false.
- **Effort:** MEDIUM

### P0.6 [SECURITY] No login rate-limit, brute-force lockout, or captcha on /auth/login
- **File:** `backend/app/api/v1/auth.py:POST /auth/login — lines 20-26; no slowapi, no failed-attempt counter, no Admin.failed_attempts column`
- **Issue:** `/auth/login` has zero throttling. There is no `failed_login_count` / `locked_until` column on `Admin`, no IP-based rate limiter, no exponential back-off, and the only mitigation is bcrypt's intrinsic ~100 ms cost. A 4-camera site on a flat LAN allows an attacker on the same network to brute-force at ~10 req/s — `ChangeMe@123` and most office passwords fall in hours.
- **Impact:** With no HTTPS in front of the API (also flagged) and a long-lived dev default password, a single compromised office laptop on 192.168.1.x can pop SUPER_ADMIN within a working day. No alert is raised — only a generic 401 log line.
- **Fix:** Add `failed_attempts` and `locked_until` columns on `Admin`. After 5 consecutive failures, lock the account for an exponentially-growing window (capped at 1 h). Also add an IP-keyed slowapi limiter (5/min) on `/auth/login` as defense in depth. Log to a new audit_log table on lock-out so the operator can see the event.
- **Effort:** MEDIUM

### P0.7 [PRIVACY_COMPLIANCE] Soft-deleted employees keep biometric data forever (DPDP)
- **File:** `backend/app/api/v1/employees.py:lines 106-117 (deactivate_employee)`
- **Issue:** DELETE /employees/{id} only flips `is_active=False`. The employee's face images on disk (storage/training_images/<code>/), the EmployeeFaceImage rows, and the L2-normalized face embeddings (EmployeeFaceEmbedding.vector) all remain indefinitely. There is no purge endpoint, no retention job, and no admin UI to actually erase biometric data. The cache filters by is_active=True so recognition stops, but the biometric template — which under India's DPDP Act 2023 is sensitive personal data — is still on disk and in the DB long after the data subject has left the organisation.
- **Impact:** Direct DPDP Act 2023 violation: failure to delete personal data when the purpose is fulfilled (Sec 8(7)) and inability to honour a Data Principal's right to erasure (Sec 12). Also leaks past employees' biometrics if the box is later compromised. Over years this also bloats the embedding matrix, slowing every recognition pass.
- **Fix:** Add a SUPER_ADMIN endpoint (e.g. POST /employees/{id}/purge_biometrics) that, in one transaction, deletes EmployeeFaceEmbedding rows, EmployeeFaceImage rows, the training folder on disk (storage/training_images/<employee_code>), and reloads the embedding cache. Also schedule an automatic purge N days after deactivation (configurable in attendance_settings) and write to a new audit_log table so the deletion is provable.
- **Effort:** MEDIUM

### P0.8 [DEPLOYMENT_OPS] No backup strategy or audit log — biometric system has no recovery path
- **File:** `DEPLOYMENT:no backup script, no audit_log table, no docker-compose, no service supervisor`
- **Issue:** Single Windows 10 PC, local Postgres 16, no replica, no documented pg_dump cadence, no encrypted off-box backup target, no tested restore procedure. There is also no audit_log table — manual event creation/deletion, login attempts, settings changes, employee deactivation, biometric deletion (when implemented), and promotion of unknown clusters all happen with `is_manual=True` or `corrected_by=admin_id` annotations on individual rows but never produce a chronological audit trail. Combined with no DPDP-compliant erasure path (see soft-delete finding), there is no way to prove who saw or changed what biometric data when.
- **Impact:** A single SSD failure or ransomware hit (Windows endpoint with no AV, RDP, and on the office LAN) loses every face template, every attendance event, every audit clue. Recovery is impossible. Under DPDP Sec 8(5) and Sec 12, the data fiduciary must be able to demonstrate compliance — without an audit log, that is impossible.
- **Fix:** (1) Add a Windows Task Scheduler entry that runs `pg_dump -Fc -f \\NAS\backup\ai-attendance-YYYYMMDD.dump` daily, encrypted with 7-Zip AES-256, and a documented restore drill. (2) Create an `audit_log(id, ts, actor_admin_id, action, target_type, target_id, ip, details_json)` table and write to it from every privileged endpoint (login/logout, employee CRUD, biometric delete, settings change, manual event, day close, promotion/recluster, snapshot purge). (3) Install NSSM or windows-service-wrapper so uvicorn auto-restarts on reboot/crash.
- **Effort:** MEDIUM

### P0.9 [FRONTEND_RESILIENCE] No React error boundaries anywhere — single render error white-screens the whole admin panel
- **File:** `frontend/app/layout.tsx:entire frontend tree (also: app/(dashboard)/layout.tsx, app/(auth)/layout.tsx)`
- **Issue:** There are zero `error.tsx`, `global-error.tsx`, or ErrorBoundary components in the tree (verified via Glob: `frontend/**/error.tsx`, `frontend/**/global-error.tsx`, `**/ErrorBoundary*` all return 0 matches). A single uncaught render error in any child — e.g. `parseISO(null)` throwing, a malformed snapshot URL, a missing nullable employee field returned by a future API version — unmounts the entire React tree and shows a blank page. The operator's only fix is a hard reload, and they get zero on-screen indication of what went wrong.
- **Impact:** In a 24/7 attendance kiosk that runs unattended for months, any backend schema drift, an unexpected null, or a transient JS error nukes the dashboard. Live View, Presence, and Reports all go blank simultaneously, even though the camera workers are fine. The operator only learns from a phone call.
- **Fix:** Add Next 15 error boundaries at three levels: `frontend/app/global-error.tsx` (root catastrophe — must render full HTML), `frontend/app/(dashboard)/error.tsx` (per-route, shows a retry button + error details, keeps the sidebar), and `frontend/app/(auth)/error.tsx`. Each should expose a `reset()` button and log the error to a backend endpoint so silent crashes become visible.
- **Effort:** SMALL

### P0.10 [FRONTEND_SECURITY] 401 interceptor clears cookie but never clears React Query cache or redirects
- **File:** `frontend/lib/api/client.ts:lines 62-71 (interceptors.response.use) — combined with lib/auth/context.tsx logout (line 67-71)`
- **Issue:** When any request returns 401, the interceptor calls `clearToken()` but doesn't (a) call `queryClient.clear()`, (b) push the user to /login, or (c) update the AuthContext. The dashboard layout's `useEffect` only checks `admin` state, which still holds the cached admin object. All TanStack Query results (employee list, presence, snapshots, dashboard snapshot at 15s refetch, presence at 10s refetch) stay in cache and continue rendering stale data. Verified `grep` for `queryClient.clear|qc.clear|removeQueries` returned zero hits across the entire frontend, including the logout handler in user-menu.tsx.
- **Impact:** After server-side token revocation, JWT secret rotation, or admin deactivation by a SUPER_ADMIN, a previously-logged-in admin can still see all employee names, attendance events, snapshots and biometric metadata — exfiltrating PII from a session that should be dead. On logout via UserMenu, the next admin who logs in on the same browser sees the previous admin's cached data flashing before the new fetch completes (cross-admin data leak). DPDP Act 2023 incident.
- **Fix:** In `lib/api/client.ts` interceptor: on 401 with `__auth!==false`, dispatch a global event or call a singleton like `window.location.assign('/login')` after clearing. In `lib/auth/context.tsx` `logout()`, call `useQueryClient().clear()` (or `removeQueries({queryKey: ...})`). Make sure background refetchers (which are queued in the QueryCache) are cancelled before navigation.
- **Effort:** SMALL

### P0.11 [DEPLOYMENT_OPS] No supervisor: process crash means cameras are dark until operator notices
- **File:** `DEPLOYMENT:n/a — operator runs uvicorn directly per env description`
- **Issue:** Deployment context states 'no process supervisor (no systemd, no Windows service yet)'. If the python.exe crashes, dies on OOM, or is killed by Windows Update, no automatic restart occurs. The cameras stop recording, attendance stops being captured, and nobody notices until a user complains the next morning.
- **Impact:** Any silent crash → hours-to-days of zero attendance recording. Goal is 'years without errors' — a single OOM kill makes the system fail silently for that day. Indian office staff lose attendance records with no recoverable timeline.
- **Fix:** Ship NSSM (https://nssm.cc/) installed as `ai-attendance` Windows Service with auto-restart on failure, restart delay 5s, and stdout/stderr piped to log files in `LOG_DIR`. Provide an `install-service.bat` script that does the install + sets recovery actions. Add a heartbeat health check (cron task that hits `/health` and emails on failure).
- **Effort:** SMALL

### P0.12 [SECURITY] JWT secret has no strength enforcement; dev default boots production
- **File:** `backend/app/config.py:JWT_SECRET_KEY field, line 27 (no validator)`
- **Issue:** `JWT_SECRET_KEY` is `str` with no `field_validator` to reject short/dev values. The active `.env` is documented to contain `JWT_SECRET_KEY=dev-local-secret-change-me-...`. If the operator forgets to rotate it, all signed JWTs are forgeable by anyone who has the source / sees the example. Same risk for `BOOTSTRAP_ADMIN_PASSWORD=ChangeMe@123` — there is no first-login forced password change.
- **Impact:** Anyone with knowledge of the default secret (the entire dev team, anyone who reads the GitHub repo, anyone who reads the deployment guide) can mint a SUPER_ADMIN JWT and delete employees, modify attendance, exfiltrate biometric vectors. Direct compromise of biometric data — under India DPDP Act 2023 this is a reportable breach with significant fines.
- **Fix:** Add a Pydantic validator: reject `JWT_SECRET_KEY` if shorter than 32 chars or matches a known dev-default pattern (`change-me`, `dev-`, `secret`). At boot, log.critical + raise SystemExit if `BOOTSTRAP_ADMIN_PASSWORD` is `ChangeMe@123` AND `APP_DEBUG=False`. Force the operator to set a password change on first SUPER_ADMIN login (track `must_change_password` on the Admin model).
- **Effort:** SMALL

### P0.13 [DEPLOYMENT_OPS] No DB backup strategy documented; single Postgres, no replica
- **File:** `DEPLOYMENT:n/a — environment description states 'PostgreSQL local, no replica'`
- **Issue:** No `pg_dump` cron, no `pg_basebackup` snapshot, no WAL archiving. Storage directory (snapshots, training images, models, unknowns) is on the same disk as Postgres. A single drive failure or accidental `DROP TABLE` loses every employee, every attendance record, every training image — there is no recovery path. The README mentions backups nowhere.
- **Impact:** Goal: 'years without errors' is impossible without backups. Single disk failure → total loss of attendance history and biometric training data. 100-300 employees would need to be re-enrolled from scratch (multi-day operator effort).
- **Fix:** Ship a `scripts/backup.ps1` that nightly: (1) `pg_dump` to a dated `.sql` on a different drive or USB; (2) robocopy storage/training_images to the same backup target. Document the restore procedure in README. Even basic daily local backups + manual weekly off-machine copy go a long way. Consider running `pg_basebackup` for point-in-time recovery.
- **Effort:** MEDIUM

### P0.14 [PRIVACY_COMPLIANCE] No consent record exists for any data subject (DPDP S.6)
- **File:** `backend/app/models/employee.py:schema-wide (also unknown_face.py, attendance_event.py)`
- **Issue:** The Employee table stores name/email/phone/photos/embeddings (biometric personal data under DPDP) but has NO consent_at, consent_version, consent_basis, consent_withdrawn_at columns. The UnknownFaceCapture/Cluster tables capture identifiable face crops of visitors with no recorded notice or consent. A grep for 'consent' across the entire codebase returns zero hits — there is literally no consent ledger.
- **Impact:** Under the DPDP Act 2023, processing biometric data of employees and visitors without a documented, withdrawable consent (or a valid 'legitimate use' basis) is a non-compliance event. On a complaint to the Data Protection Board, the operator cannot prove lawful basis and faces penalties up to INR 250 crore. The system cannot honor a withdrawal request because there is no record to flip.
- **Fix:** Add an employee_consents table (employee_id, purpose, lawful_basis, consent_text_version, signed_at, withdrawn_at, witnessed_by_admin_id) and a visitor_notice table (camera_id, location, posted_notice_version, effective_from). Block /promote/* and training endpoints unless a consent row exists. Ship a template Indian-language privacy notice as docs/PRIVACY_NOTICE.md.template.
- **Effort:** MEDIUM

### P0.15 [PRIVACY_COMPLIANCE] No Right-to-Erasure / Right-to-Access endpoints (DPDP S.12-13)
- **File:** `backend/app/api/v1/employees.py:lines 106-117 (deactivate_employee)`
- **Issue:** DELETE /employees/{id} sets `is_active = False` — soft delete. The face_images, face_embeddings, attendance_events, snapshots on disk, and all daily_attendance rows remain forever. There is no /employees/{id}/erase or /employees/{id}/export endpoint, and no equivalent for unknown clusters that turned out to be a known visitor who later asks for their data to be deleted.
- **Impact:** When an employee leaves and asks for erasure (DPDP S.12), or files an access request (S.11), the operator has no API to satisfy the request within the statutory window. Biometric data of ex-employees accumulates indefinitely, breaching the 'no longer necessary for the purpose' clause.
- **Fix:** Add `POST /employees/{id}/erase` that hard-deletes face_images on disk + face_embeddings + snapshots (rewriting attendance_events.snapshot_path=NULL) and a tombstone row recording who erased what. Add `GET /employees/{id}/export.json` that bundles every PII row for the subject. Document both in the SOP.
- **Effort:** MEDIUM

### P0.16 [PRIVACY_COMPLIANCE] Plain-text HTTP — biometric data and JWTs travel unencrypted
- **File:** `backend/app/main.py:uvicorn run, README.md line 41`
- **Issue:** The deployment doc says `uvicorn app.main:app --host 0.0.0.0 --port 8000` — no TLS. No reverse proxy is shipped. Any device on the office LAN can sniff the JWT bearer token, the face JPGs streamed back from /snapshots/by-event/{id}, the captured unknown face images, and the RTSP credentials embedded in GET /cameras responses. The CORS middleware permits credentialed cross-origin without TLS (`allow_credentials=True`).
- **Impact:** Under DPDP S.8(5), the data fiduciary must take 'reasonable security safeguards' — plain HTTP for biometric PII does not qualify. A breach via LAN sniffing triggers the 72-hour notification obligation. Stolen JWTs (24-hour expiry, line 13 of .env) yield full SUPER_ADMIN access for a day.
- **Fix:** Ship a Caddy or nginx reverse-proxy config with auto-generated self-signed cert (or Let's Encrypt for internal domain) bound to 0.0.0.0:443. Bind uvicorn to 127.0.0.1:8000. Update README. Add a startup check that refuses to start with APP_HOST=0.0.0.0 unless TLS_DISABLED_ACK=true.
- **Effort:** MEDIUM

### P0.17 [DEPLOYMENT_OPS] No process supervisor: uvicorn dies with terminal/reboot
- **File:** `DEPLOYMENT:README.md:23 — `uvicorn app.main:app --host 0.0.0.0 --port 8000``
- **Issue:** The system is started by manually running `uvicorn` (and `next start`) in a terminal. There is no Windows Service, no NSSM wrapper, no Task Scheduler `at startup` entry, no batch file in Startup, no Docker auto-restart. Closing the terminal or signing the user out kills the API and frontend; a Windows Update reboot leaves attendance offline indefinitely; an unhandled exception during FastAPI lifespan (see app/main.py:24-46 — no try/except around `bootstrap_admin`, `FaceService.load`, `camera_manager.start_all`) crashes the whole process with no restart.
- **Impact:** First reboot, first power blip, first OS update cycle, the office walks in and the attendance system is down. Nobody is notified. Days of attendance are silently lost — events from the cameras are never recorded.
- **Fix:** Wrap both uvicorn and `next start` in NSSM as Windows Services with `AppExit = Restart` and `AppRestartDelay = 5000`. Set service start to Automatic. Add a Windows Task Scheduler ON_EVENT trigger on EventID 6005 (system startup) as a belt-and-suspenders. Add a try/except around the entire lifespan body in app/main.py so a single transient failure (DB blip on boot) does not kill the process — log loudly and continue.
- **Effort:** MEDIUM

### P0.18 [DATA_INTEGRITY] No automated PostgreSQL backups — total data loss on drive failure
- **File:** `DEPLOYMENT:repository-wide — no pg_dump scripts, no scheduled task, no backup docs`
- **Issue:** There is no `pg_dump` script anywhere in the repo, no Windows Task Scheduler job, no off-host copy. Months of biometric embeddings, attendance events, employee roster, and snapshots live on one consumer-grade Windows 10 PC's C:\ drive with no replica. The prompt mentions a `migration_bundle/RESTORE_INSTRUCTIONS.md` — that path does not exist in this repository (`Get-ChildItem -Recurse -Filter migration_bundle` returns nothing), so even the one-time-restore guide is absent.
- **Impact:** When the SSD fails (consumer drives die — it is a matter of when, not if), the entire attendance history disappears. Re-enrolling 100-300 employees' faces is days of work, and historical events for payroll/audit are gone forever.
- **Fix:** Ship `ops/backup.ps1`: `pg_dump --format=custom ai_attendance > backups\\ai_attendance_YYYYMMDD.dump` + `robocopy storage\\snapshots backups\\snapshots /MIR`. Register as nightly Task Scheduler job at 02:00. Add a second copy to a USB drive or a network SMB share. Write `BACKUP.md` and `RESTORE.md` runbooks. Add a `/admin/backup-status` endpoint that returns the age of the most recent .dump so the UI can show a red banner if it is more than 36h old.
- **Effort:** MEDIUM

### P0.19 [EDGE_CASES] storage/ grows unbounded — disk full eventually halts pipeline
- **File:** `backend/app/services/snapshot_service.py:save_event_snapshot:45-79 (and unknown_capture_service.py:209)`
- **Issue:** Snapshots, unknown-face captures, and training images write JPEGs to `./storage/...` with no automatic retention. The `purge_before` method exists (snapshot_service.py:116-164) but is only invoked when an admin clicks a button — there is no scheduler in the codebase (only one comment in unknown_recluster_service.py mentions 'safe to schedule (e.g. nightly cron)'). At ~100 employees × ~6 events/day × ~80 KB = ~50 MB/day plus unknowns, the C:\ drive fills in 12-24 months. Once ENOSPC hits, `write_jpeg` raises, the worker increments `last_error`, but `attendance_service.process_auto_event` writes the snapshot path BEFORE the DB commit — so disk-full means events stop being recorded, silently.
- **Impact:** After ~1-2 years the drive fills, snapshot writes fail, attendance events stop being persisted (because the snapshot save raises before `event_repo.add`), and the system goes dark with no operator alert. PostgreSQL itself will also stop accepting writes when WAL cannot grow, corrupting the active session.
- **Fix:** Add a background scheduler (APScheduler) started in lifespan: nightly call `SnapshotService().purge_before(today - retention_days)` driven by a new `attendance_settings.snapshot_retention_days` setting (default 180). Add a free-disk health check that surfaces in `/admin/live-status` and refuses to write snapshots once free space drops below 5 GB (skip save, log, but still create the DB event). Add a daily log line with disk usage so trends are visible.
- **Effort:** MEDIUM

### P0.20 [SECURITY] JWT_SECRET_KEY default 'dev-local-secret' is never enforced in production
- **File:** `backend/app/config.py:Settings.JWT_SECRET_KEY (line 27); current `.env` line 11 ships `JWT_SECRET_KEY=dev-local-secret-change-me-...``
- **Issue:** The config does not validate that `JWT_SECRET_KEY` differs from a known-bad placeholder, nor that it is of sufficient entropy. The shipped `.env` carries `dev-local-secret-change-me-to-a-long-random-string-xxxxxxxxxxx` and `APP_DEBUG=true`. There is no startup check; operators copy `.env.example`, never edit it, and run the system on the install-default secret. Any attacker who reads the GitHub repo or guesses the placeholder can forge HS256 tokens for any user_id, bypass auth entirely, and obtain admin access.
- **Impact:** Any visitor on the same office Wi-Fi (or anyone who chains a Wi-Fi compromise) can mint a SUPER_ADMIN JWT, read all biometric data, modify attendance records, and delete events. Under India DPDP 2023 this is a reportable breach of sensitive personal data.
- **Fix:** Add a `@field_validator('JWT_SECRET_KEY')` in config.py that rejects any value containing 'change-me' / 'dev-local' / shorter than 32 chars AND raises at boot when `APP_DEBUG=False`. Generate the secret automatically on first run if missing (`secrets.token_urlsafe(64)`) and write it back to `.env` with a comment. Also reject `APP_DEBUG=true` when `CORS_ALLOW_ORIGINS` contains a non-localhost origin.
- **Effort:** SMALL

### P0.21 [DEPLOYMENT_OPS] Only one admin can ever be created — single point of lockout
- **File:** `backend/app/api/v1/auth.py:entire file — no admin-create endpoint; bootstrap_admin (auth_service.py:70) only runs when admins table is empty`
- **Issue:** The auth router exposes only `/login`, `/me`, `/change-password`. There is no endpoint to create a second admin, reset another admin's password, or for SUPER_ADMIN to add an ADMIN. `bootstrap_admin()` short-circuits if any admin already exists. If the SUPER_ADMIN forgets their password, OR if `BOOTSTRAP_ADMIN_PASSWORD` is changed in `.env` after first boot (it has no effect since admins.count() > 0), OR if `.env` is lost, the operator has zero in-application recovery path — they must shell into Postgres and UPDATE the password_hash directly. Also no second admin means no oversight or coverage when the primary admin is on leave.
- **Impact:** One forgotten password = system permanently locked, no way to view attendance, no way to add new employees, no way to change settings. The operator is stuck calling the developer to manually run SQL.
- **Fix:** Add `POST /api/v1/admins` (SUPER_ADMIN only) to create additional admins, `POST /api/v1/admins/{id}/reset-password` to reset another admin's password, `GET /api/v1/admins` to list them, plus a CLI command `python -m app.cli reset_admin <username>` that runs without HTTP and prompts at the console — gives a documented offline recovery. Strongly recommend forcing creation of a second SUPER_ADMIN on first login as a 'recovery contact'.
- **Effort:** MEDIUM


## P1_IMPORTANT (70 items) — will cause incidents over months/years

### P1.1 [OBSERVABILITY] No audit trail for destructive ops on employees, cameras, settings
- **File:** `backend/app/api/v1/employees.py:deactivate_employee L106-116; settings PATCH backend/app/api/v1/settings.py L25-34; cameras PATCH/DELETE backend/app/api/v1/cameras.py L251-298`
- **Issue:** Only AttendanceEvent has a corrected_by/correction trail. There is no audit log table or row recording WHO deactivated an employee, WHO changed face_match_threshold (only `updated_by` survives — overwritten each PATCH), WHO deleted/edited a camera, WHO added or removed an admin. The settings model stores `updated_by` but no previous value or timestamp per change, so there is no way to answer 'why did recognition stop working last Tuesday — did someone bump the threshold?'
- **Fix:** Add an `audit_log` table (id, admin_id, action, entity_type, entity_id, before_json, after_json, ip_address, at) and a small helper called from PATCH/DELETE handlers on employees, cameras, settings, and admins. At minimum, log settings changes (key, old_value, new_value, admin_id) since face_match_threshold and cooldown materially affect attendance correctness.
- **Effort:** MEDIUM

### P1.2 [OBSERVABILITY] Worker stats reset on every process restart — no persistence
- **File:** `backend/app/workers/camera_worker.py:WorkerStats L36-50; CameraManager._lifetime L65 backend/app/workers/camera_manager.py`
- **Issue:** `WorkerStats.processed_frames/events_generated/auto_enrollments/unknown_captures/total_reconnects` and `CameraManager._lifetime['restarts']` all live entirely in RAM. Every uvicorn restart (config change, OS reboot, crash, upgrade) zeroes them. There is no per-camera daily counter persisted to DB.
- **Fix:** Add a `camera_daily_stats` table (camera_id, work_date, processed_frames, events, reconnects, total_downtime_seconds) flushed by the health loop every minute. Optionally also persist `camera_health_event` rows (camera_id, state_transition, at, reason) so 'when did camera X last go offline' has a real answer.
- **Effort:** MEDIUM

### P1.3 [OBSERVABILITY] /health endpoint is trivial — does not check DB, model, storage
- **File:** `backend/app/main.py:L80-82`
- **Issue:** `/health` returns `{"status": "ok"}` unconditionally — it does not SELECT 1 on Postgres, does not verify the embedding cache loaded, does not verify InsightFace is loaded, does not check that storage roots are writable, does not check free disk. Any of these can be silently broken while /health still says ok.
- **Fix:** Split into `/health/live` (process up — keep cheap) and `/health/ready` that runs: SELECT 1 with a 2s timeout, `face_service._loaded` check, `embedding_cache.size() >= 0`, `os.access(STORAGE_ROOT, os.W_OK)`, and `shutil.disk_usage(STORAGE_ROOT).free` (with threshold). Return 503 with a JSON body listing which probes failed. Document the endpoint as the supervisor probe.
- **Effort:** SMALL

### P1.4 [OBSERVABILITY] Background jobs (day-close, recluster, purge) have no run history
- **File:** `backend/app/services/unknown_purge_service.py:file-wide; also unknown_recluster_service.py, daily_attendance_service.py close_day`
- **Issue:** Day-close, HDBSCAN recluster, and unknowns purge log to file but never persist a `job_run` row with last_run_at, status (OK/FAILED), duration_ms, error_message, items_processed. The frontend has no way to display 'last day-close: 2026-06-05 23:55, OK, 247 employees' or 'last purge: failed 3 days ago — disk filling'.
- **Fix:** Add a `job_run` table (job_name, started_at, finished_at, status, duration_ms, items_processed, error) and wrap each background job's entry point. Expose `GET /api/v1/admin/jobs` returning last-N runs per job, and surface 'last run + status' tiles on the dashboard.
- **Effort:** MEDIUM

### P1.5 [RELIABILITY] Embedding cache rebuild failure crashes app startup silently
- **File:** `backend/app/services/embedding_cache.py:load_from_db L42-80; called from backend/app/main.py L35`
- **Issue:** If `load_from_db` raises (Postgres slow during boot, OperationalError, corrupt embedding row that throws before the per-row try), the FastAPI lifespan raises and uvicorn exits. There is no fallback to a stale on-disk snapshot of the cache; no metric/event for 'cache last-rebuilt-at'; the per-row try only catches `ValueError` from `_unpack`, not other failures. Manual rebuild via `/training/rebuild-cache` has no return body indicating whether it succeeded or how many vectors it loaded.
- **Fix:** Catch broader exceptions per-row inside `load_from_db` (log + skip + count). Track `last_rebuilt_at`, `vectors_loaded`, `vectors_skipped` on the cache and expose them via `/health/ready` and the admin dashboard. In `main.lifespan`, log-and-continue on cache load failure with a degraded-mode banner instead of crashing.
- **Effort:** SMALL

### P1.6 [RELIABILITY] InsightFace model file corruption not detected or recovered
- **File:** `backend/app/services/face_service.py:load L31-54`
- **Issue:** Model files live under `./storage/models/buffalo_l/*.onnx`. If a file becomes corrupt (power loss mid-download, antivirus quarantine, disk error), `FaceAnalysis(...)` raises generically. There is no sha256 verification of the model files at startup, no auto-recovery (download / unpack from a known-good copy), and no operator-readable check.
- **Fix:** Ship a manifest of expected model files + sha256 in `app/services/face_service.py`. At startup verify each file exists and hashes match; on mismatch, log a fatal-grade message that names the file and (optionally) auto-restore from a pinned `./storage/models/.backup` directory shipped with the install.
- **Effort:** MEDIUM

### P1.7 [SECURITY] No global exception handler — DB/IO errors leak stack traces to user
- **File:** `backend/app/main.py:create_app L56-85`
- **Issue:** Only `AppError` is handled. A `sqlalchemy.exc.OperationalError` (PG restarting, connection killed, deadlock), `psycopg2.errors.*`, `OSError` on snapshot write, or any AttributeError becomes FastAPI's default 500 with the full stack trace in the response body when `APP_DEBUG=True`, and an opaque 'Internal Server Error' otherwise — but no structured logging tying the error to the request that caused it.
- **Fix:** Add a catch-all `@app.exception_handler(Exception)` that logs with a generated request_id and returns a sanitized 500/503 JSON. Map `sqlalchemy.exc.OperationalError`/`DBAPIError` (connection lost) to 503 with a friendly message. Add a request-id middleware that puts an ID in every log line for correlation.
- **Effort:** SMALL

### P1.8 [SECURITY] No failed-login tracking, no rate limit, no lockout
- **File:** `backend/app/services/auth_service.py:authenticate L28-37`
- **Issue:** `last_login_at` is updated on success but failed attempts are not counted, logged at WARN, or rate-limited. The `/auth/login` endpoint has no IP-based throttle. A 24-hour brute force against `BOOTSTRAP_ADMIN_USERNAME='admin'` with `BOOTSTRAP_ADMIN_PASSWORD='ChangeMe@123'` is unopposed and invisible.
- **Fix:** Add columns `failed_login_count`, `last_failed_login_at`, `locked_until` to admins. On failure, increment + log WARN with client IP; lock the account for N minutes after K consecutive failures. Add a slowapi/limits-based rate limit on `/auth/login` (e.g. 10/min per IP). Surface a `/api/v1/admin/security/failed-logins` recent-list endpoint.
- **Effort:** MEDIUM

### P1.9 [OBSERVABILITY] Camera health is current-state-only — no history of outages
- **File:** `backend/app/workers/camera_manager.py:status() L267-298; _health_loop L300-366`
- **Issue:** `/cameras/health` returns the *current* health_state and last_error string but no event history. There is no record of 'camera 3 went OFFLINE 2026-05-20 14:02 → ONLINE 14:11 (9 min outage)'. The `_last_health_restart` dict tracks throttling, not history. The frontend cannot answer 'which camera had the most outages last week'.
- **Fix:** Add a `camera_health_event` table (camera_id, event_type=ONLINE/OFFLINE/DEGRADED/RESTARTED, reason, at). The health loop writes a row on every state transition. Expose `GET /api/v1/cameras/{id}/history?days=7` and render a per-camera uptime timeline in the frontend.
- **Effort:** MEDIUM

### P1.10 [OBSERVABILITY] Diagnostic detection log is INFO — saturates 500 MB log cap quickly
- **File:** `backend/app/workers/camera_worker.py:L276-283 detected log; L387-391 unknown skipped log`
- **Issue:** At 1 detection/sec/camera × 4 cameras × ~200 bytes/line × 8 work-hours = ~23 MB/day from the 'detected N face(s)' line alone, plus the 'unknown skipped' INFO line on every unrecognized face during high traffic. With LOG_MAX_BYTES=100 MB and BACKUP_COUNT=5 (500 MB cap), retention is ~3 weeks in light deployments and only a few days when unknowns capture is enabled and the office is busy. The TODO 'drop back to DEBUG once tuning is settled' is unaddressed.
- **Fix:** Move the per-frame `detected N face(s)` line and `unknown skipped reason=` line back to DEBUG. Replace with a per-minute aggregated INFO line per camera ('cam=lobby 1m: frames=60 detected=12 unknown_skipped=3 events=2'). Keep ERROR/WARN at INFO level so important signals survive rotation.
- **Effort:** SMALL

### P1.11 [PERFORMANCE] EmbeddingCache fully rebuilt on every auto-enroll
- **File:** `backend/app/services/training_service.py:auto_enroll_from_frame line 273; enroll line 136; capture_and_enroll line 211; delete_image line 303`
- **Issue:** After every successful auto-enrollment from a camera tick, `auto_enroll_from_frame` calls `self.cache.load_from_db()`, which re-queries every active embedding row, decodes/L2-normalizes each one and rebuilds the global float32 matrix. With 300 employees x 20 embeddings = 6000 vectors x 512 dims, this is ~12 MB of allocation + a SELECT JOIN every time, while holding the embedding cache lock. Auto-enroll runs on the camera worker thread, so it can stall recognition for hundreds of ms. With unknown_promotion and admin enrollments doing the same thing concurrently, the cache lock becomes a worker-blocker.
- **Fix:** Add an `append_employee(employee_id, vectors)` method to EmbeddingCache that vstacks the new vectors onto the existing matrix under the lock without touching the DB. Use that from auto_enroll/single image add. Keep load_from_db() only for full rebuilds (delete, bulk import, manual reload). Even simpler: schedule the load_from_db() onto a debounced background worker that coalesces multiple writes inside a 5s window.
- **Effort:** MEDIUM

### P1.12 [PERFORMANCE] Snapshot writes happen synchronously on the worker thread
- **File:** `backend/app/services/snapshot_service.py:save_event_snapshot lines 45-80; called from AttendanceService.process_auto_event in the camera worker tick`
- **Issue:** Every accepted attendance event blocks the camera worker on: bbox crop + cv2.imencode JPEG quality 85 + filesystem mkdir + write_bytes. On Windows NTFS with antivirus scanning, write_bytes can spike to 50-200 ms. Unknown capture is also blocking (write_jpeg at quality 88 plus path build). Both run inside `session_scope()` — the DB transaction stays open until disk I/O completes.
- **Fix:** Move file writes off the DB transaction: first commit the AttendanceEvent with `snapshot_path` set to the destination path, then submit the encode+write to a small dedicated ThreadPoolExecutor (1-2 workers, bounded queue). On write failure, NULL the snapshot_path in a follow-up update. Equivalent for UnknownCaptureService — the row already has `embedding`; the JPEG is decorative.
- **Effort:** MEDIUM

### P1.13 [PERFORMANCE] Live-preview endpoint has no rate limit; each poll encodes JPEG
- **File:** `backend/app/api/v1/cameras.py:camera_preview endpoint lines 309-334; preview_service.encode_jpeg`
- **Issue:** `/cameras/{id}/preview.jpg` runs on the FastAPI event loop, copies the latest frame under the worker lock, annotates it, and `cv2.imencode`-s on every request. There is zero rate limit, no caching, no last-modified check. With 8 cameras × 600 ms refresh × 5 admin browsers open = ~67 encodes/sec. Worse, each encode runs in the asyncio thread (the endpoint is `def`, not `async def`, so FastAPI uses a threadpool, but they still contend for the GIL with workers).
- **Fix:** Cache the most recent encoded JPEG per (camera_id, annotated, quality) on the CameraWorker side with a small TTL (200-500 ms). Only re-encode when `_latest_frame_at` changes AND TTL expired. Also add a per-IP token bucket (e.g., 5 req/s) via a slowapi middleware on the preview endpoint. Or migrate to MJPEG streaming (single producer, multiple consumers) — eliminates the polling overhead.
- **Effort:** MEDIUM

### P1.14 [PERFORMANCE] close_day and recompute_range loop N×D recompute queries
- **File:** `backend/app/services/daily_attendance_service.py:close_day lines 211-239; recompute_range lines 285-296`
- **Issue:** close_day iterates one employee at a time and calls `self.event_repo.list_for_employee_between(...)` plus `recompute()` (which itself runs another `list_for_employee_between`) per employee. That's 2 queries per employee + 1 upsert. With 300 employees and a flush at the end, this is 600+ round-trips inside the `close_day` HTTP request that holds the request thread plus a DB connection for the duration. recompute_range is worse — N employees × D dates × 2 queries per recompute. A 30-day, 300-employee range = 18,000 queries blocking one API thread.
- **Fix:** (1) Replace the per-employee event fetch with one batched query: `select(AttendanceEvent).where(employee_id.in_(ids), event_time in range).order_by(employee_id, event_time)` then group in Python. (2) Wrap close_day in a background task (FastAPI BackgroundTasks or an apscheduler job) with progress reporting via a `/close-day/status?date=...` endpoint. (3) For recompute_range, chunk by week + commit between chunks to release DB locks.
- **Effort:** MEDIUM

### P1.15 [SECURITY] No max-dimension guard on incoming face images — JPEG bomb risk
- **File:** `backend/app/utils/image_utils.py:decode_image_bytes lines 9-14; used by training.upload_training_images and recognition.identify`
- **Issue:** `decode_image_bytes` decodes whatever bytes the admin uploads via cv2.imdecode. There is no `MAX_UPLOAD_BYTES`, no max-pixel guard, and no aspect-ratio check. A 50000×50000 PNG (~10MB compressed, 2.5GB decompressed) instantly OOMs the process. Even a 'normal' 8000×8000 JPEG inflates to 192 MB and runs FaceAnalysis.get() on a frame larger than its 640×640 detect size — InsightFace may misbehave or crash.
- **Fix:** In `decode_image_bytes`, check `len(data) < settings.MAX_UPLOAD_BYTES` (e.g. 10 MB), check decoded `img.shape[0]*img.shape[1] < 40_000_000` (40 megapixels), and `cv2.resize` down to `max(width,height) <= 1920` before passing to FaceService. Reject with ValidationError otherwise. Add `client_max_body_size` at the FastAPI/uvicorn level when a reverse proxy is added.
- **Effort:** SMALL

### P1.16 [PERFORMANCE] FaceService single global lock serializes all detections
- **File:** `backend/app/services/face_service.py:detect() lines 62-65 — `with self._lock: raw = app.get(frame_bgr)``
- **Issue:** Every InsightFace call (camera workers, training enroll, /recognition/identify, unknown promotion verification) acquires the same `self._lock`. At 4 cameras × 1 FPS detection it's invisible. Scale to 16 cameras × 5 FPS = 80 detection calls/sec each ~30-80 ms on CPU — wall clock 2.4 s/s, far over one core. Workers queue and frames are dropped, but the cooldown_service prevents the operator from seeing this as 'missed attendance' because most cameras would see the same person again before cooldown.
- **Fix:** Remove the `with self._lock` around `app.get()` — InsightFace's underlying ONNX Runtime session IS thread-safe for read-only inference. Keep the lock only around model load. If a particular provider needs serialization (CUDA single stream), instantiate one FaceAnalysis per CUDA device or per worker thread instead of one global. Run the smoke test: 4 threads × 1000 detects with no lock; verify no crashes (it works in production for InsightFace users on CPU).
- **Effort:** SMALL

### P1.17 [DEPLOYMENT_OPS] No scheduled job for snapshot/unknown purge or DB vacuum
- **File:** `DEPLOYMENT:No scheduler anywhere; snapshots.purge and unknowns.purge are manual API endpoints only`
- **Issue:** Both `/snapshots/purge?before_date=` and `/unknowns/purge` exist but are only invoked when an admin clicks. There's no background job to enforce `unknown_retention_days` or to purge old snapshots automatically. After a year of unattended operation, the snapshots directory accumulates millions of JPGs and the `attendance_events` table millions of rows — neither is reaped. Postgres autovacuum on a 1M+ row events table without proper tuning leads to bloat.
- **Fix:** Add APScheduler (or a small native thread loop) started in main.lifespan that runs nightly at 02:30 local: (1) UnknownPurgeService(db).purge() for >retention_days; (2) SnapshotService().purge_before(today-snapshot_retention_days) — add a new setting; (3) DailyAttendanceService.close_day(yesterday) — auto-close yesterday's day; (4) `db.execute('VACUUM ANALYZE attendance_events')` weekly. Surface last-run timestamps in /admin/maintenance for visibility.
- **Effort:** MEDIUM

### P1.18 [SECURITY] Tokens are not revoked on password change, role change, or logout
- **File:** `backend/app/services/auth_service.py:change_password() lines 60-67; no /auth/logout in auth.py`
- **Issue:** `change_password` updates `password_hash` but does NOT bump a token version, deny-list the old token, or shorten its `exp`. The same JWT remains valid for the rest of its 24 h lifetime even after a deliberate password reset (e.g. operator suspects a leak). There is also no `/auth/logout` endpoint, and `clearToken()` on the frontend only deletes the cookie client-side — the JWT is still acceptable server-side.
- **Fix:** Add `token_version: int` column to `Admin` (start at 1). Include it as a claim `tv` in every JWT. In `resolve_admin`, require `payload['tv'] == admin.token_version`. Bump `token_version` on password change, role change, and explicit `POST /auth/logout`. This is server-side revocation without needing a Redis denylist.
- **Effort:** SMALL

### P1.19 [SECURITY] No file-upload size limit or magic-byte check on training/identify uploads
- **File:** `backend/app/api/v1/training.py:upload_training_images() lines 48-77; recognition.identify() in recognition.py`
- **Issue:** `POST /employees/{id}/training/images` accepts up to 20 `UploadFile`s with no `max_size` check; the handler calls `await f.read()` on each. `decode_image_bytes` then hands the raw buffer to `cv2.imdecode`. There is no content-type allowlist, no JPEG/PNG magic-byte sniff, no max-pixel-dimension limit, and no body-size cap configured on uvicorn. The same applies to `/recognition/identify` and the unknowns image flow.
- **Fix:** Validate `UploadFile.content_type` against a `{'image/jpeg','image/png'}` allowlist. Stream-read with a hard cap (e.g. 10 MB/file, 100 MB total) and 413 on overflow. After decode, check `img.shape[0] * img.shape[1] <= 25_000_000` (5000x5000) and reject otherwise. Configure uvicorn with `--limit-max-requests` and a reverse proxy with `client_max_body_size`.
- **Effort:** SMALL

### P1.20 [SECURITY] RTSP credentials are stored & returned in plaintext to every authenticated user
- **File:** `backend/app/models/camera.py:Camera.rtsp_url line 15; CameraRead schema in backend/app/schemas/camera.py line 136; GET /cameras only requires get_current_admin`
- **Issue:** `Camera.rtsp_url` stores the full URL including `user:password@host` in plaintext in Postgres. `GET /api/v1/cameras` and `GET /api/v1/cameras/{id}` return `rtsp_url` verbatim and are gated only by `get_current_admin` — a VIEWER (lowest role, intended for read-only dashboard staff) can fetch every camera password in cleartext. The smart-connect response also returns the working URL with embedded creds. Postgres backups (or pg_dump tickets) carry the same plaintext.
- **Fix:** Split `Camera.rtsp_url` into a non-secret `rtsp_url_template` (host/path) and an encrypted `credentials_ciphertext` column encrypted with a key derived from JWT_SECRET_KEY (or a dedicated FERNET key). Reassemble at worker-start. In `CameraRead`, mask the password (`rtsp://user:****@host/...`) for non-SUPER_ADMIN roles. Never include the raw URL in SmartConnect responses.
- **Effort:** MEDIUM

### P1.21 [PRIVACY_COMPLIANCE] No audit log of admin actions (delete, update, settings change, day-close)
- **File:** `backend/app/models:no audit_log model exists; grep audit returned only cooldown/cluster matches`
- **Issue:** There is no `audit_log` table and no service writing one. Destructive operations — `DELETE /employees/{id}` (deactivate), `DELETE /cameras/{id}`, `DELETE /attendance/events/{id}`, `POST /unknowns/purge`, `POST /attendance/reopen-day`, `PATCH /settings`, `POST /auth/change-password` — produce only an `INFO` log line at best. There is no DB-level trail of who deleted what, when, from which IP, and with what payload.
- **Fix:** Create `audit_logs(id, admin_id, action, target_type, target_id, before_json, after_json, ip, user_agent, ts)` table + an `AuditService.record()` helper. Call it from every endpoint that mutates Employee, Camera, Settings, AttendanceEvent, or Admin (login success/failure, password change). Add a SUPER_ADMIN-only `/audit-logs` query endpoint and retain rows for at least 3 years.
- **Effort:** LARGE

### P1.22 [SECURITY] API is HTTP-only — credentials and JWTs travel in cleartext on the LAN
- **File:** `DEPLOYMENT:uvicorn started without ssl_keyfile/ssl_certfile; no reverse proxy`
- **Issue:** The deployment context states uvicorn directly serves the API with no reverse proxy. There is no TLS config, no certificate provisioning, and `frontend/lib/auth/session.ts` only sets the cookie `secure` flag when `NODE_ENV === 'production'` (which it usually is, but the Bearer header itself rides over plain HTTP regardless). Camera passwords, JWTs, and login credentials cross the LAN unencrypted.
- **Fix:** Ship a `Caddyfile` (or nginx config) snippet plus a self-signed cert auto-generation script in the deploy package; bind uvicorn to 127.0.0.1 and have Caddy terminate HTTPS on 0.0.0.0:443 with HSTS. Document `mkcert` for trusted local CA. Make `NEXT_PUBLIC_API_URL` default to `https://`.
- **Effort:** MEDIUM

### P1.23 [FRONTEND_SECURITY] Frontend stores JWT in a JS-readable cookie (no httpOnly) — XSS = total account takeover
- **File:** `frontend/lib/auth/session.ts:setToken() lines 11-17`
- **Issue:** `Cookies.set(TOKEN_COOKIE, ...)` from `js-cookie` cannot set `httpOnly`. The JWT is therefore readable from any script context, including injected third-party scripts and any XSS through user-controlled fields (employee name, camera location/description, unknown-cluster label — all reflected in the UI). With `sameSite: 'lax'` and no CSP, the protection surface is thin.
- **Fix:** Issue the token as an httpOnly `Set-Cookie` from the backend `/auth/login` (Secure, SameSite=Strict). Have the frontend rely on the browser sending the cookie automatically and remove `Authorization: Bearer` plumbing for the same origin. Add a strict Content-Security-Policy header (no `unsafe-inline`) in `next.config` headers.
- **Effort:** MEDIUM

### P1.24 [RELIABILITY] No SUPER_ADMIN bootstrap of additional admins — single point of failure
- **File:** `backend/app/api/v1:no /admins router exists`
- **Issue:** There is no admin-management endpoint: no `POST /admins`, `PATCH /admins/{id}`, `DELETE /admins/{id}`, or password-reset. The only path to having a second admin is direct DB INSERT. If the lone SUPER_ADMIN forgets their password, the operator is locked out of their own attendance system with no recovery flow.
- **Fix:** Add a SUPER_ADMIN-only `/admins` CRUD router (create, list, deactivate, force-password-reset). Add a `python -m app.cli reset-admin-password <username>` Click command for the truly-locked-out case. Document both in the runbook.
- **Effort:** MEDIUM

### P1.25 [DATA_INTEGRITY] Event delete leaves orphan snapshot JPGs on disk
- **File:** `backend/app/services/attendance_service.py:delete_event lines 181-189`
- **Issue:** AttendanceService.delete_event removes the DB row but never unlinks the file referenced by event.snapshot_path. The same gap exists for update_event when the event is deleted/reassigned, and for the orphan tombstones produced when a camera is later deleted (camera_id is SET NULL but the snapshot file is still on disk). Over years of admins correcting events, orphan JPGs accumulate forever in storage/snapshots/YYYY-MM-DD/<employee_id>/.
- **Fix:** In delete_event, capture event.snapshot_path before calling event_repo.delete(event), then attempt Path(snapshot_path).unlink(missing_ok=True) inside a try/except OSError that logs but does not raise. Apply the same pattern in any code path that nullifies snapshot_path. Add a periodic reconciliation job that walks storage/snapshots and deletes files whose absolute path is no longer referenced by any AttendanceEvent row.
- **Effort:** SMALL

### P1.26 [DATA_INTEGRITY] unknown_max_total_captures setting is never enforced
- **File:** `backend/app/services/unknown_capture_service.py:_process pipeline, steps 4-6 (lines 190-229)`
- **Issue:** attendance_settings.unknown_max_total_captures (default 5000) is loaded by SettingsService and serialised in the schema, but UnknownCaptureService never queries the global KEEP count and never blocks new captures when the cap is exceeded. Per-cluster cap (_PER_CLUSTER_KEEP_CAP=30) is enforced; the global cap is purely cosmetic. UnknownPurgeService only deletes IGNORED/MERGED clusters older than `unknown_retention_days`; long-lived PENDING clusters and KEEP captures inside them are never pruned.
- **Fix:** Before persisting a capture, call UnknownCaptureRepository.count_keep_total(model_name=self._model_name) and short-circuit with reason="global_cap" when the count is at or above settings.unknown_max_total_captures. Optionally also auto-mark the oldest PENDING clusters as IGNORED once the cap is reached, so the existing purge job can reclaim them.
- **Effort:** SMALL

### P1.27 [DATA_INTEGRITY] daily_attendance status enum cannot express leave/holiday/half-day
- **File:** `backend/migrations/versions/0001_initial.py:session_status enum, lines 211-216`
- **Issue:** session_status has only PRESENT / INCOMPLETE / ABSENT. Real Indian office attendance needs at least HALF_DAY, LEAVE, HOLIDAY, and ON_DUTY (off-site) — every HR rollup downstream of this table will eventually need them. Adding a value later requires ALTER TYPE … ADD VALUE inside a migration AND every downstream consumer (dashboard, reports, frontend filters) needs to be updated atomically. Because Postgres ALTER TYPE ADD VALUE cannot run inside a transaction in older versions, doing it in an autogenerated migration tends to fail.
- **Fix:** Introduce the canonical superset now: add HALF_DAY, LEAVE, HOLIDAY, ON_DUTY values to session_status (use op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'HALF_DAY'") outside a transaction). Document the new states in core/constants.py with comments that current code treats them as INCOMPLETE for backwards compat. Add a leave_type/holiday lookup table so close_day knows which days to skip.
- **Effort:** MEDIUM

### P1.28 [EDGE_CASES] DST/clock-skew not modelled; local-day boundary breaks under timezone changes
- **File:** `backend/app/utils/time_utils.py:local_day_bounds, lines 35-39 and local_date_of line 42`
- **Issue:** All day-boundary math goes through local_day_bounds(local_date) which combines midnight in the configured timezone. India does not observe DST, so this looks safe today. But (a) settings.TIMEZONE is operator-editable — if it ever changes from Asia/Kolkata to, e.g., Asia/Tehran (which does have DST) or anywhere else that observes DST, the existing daily_attendance.work_date rows silently misalign with their underlying events; (b) if the OS clock jumps (NTP correction, BIOS reset after power loss, manual change), an event_time can be inserted with the wrong UTC value and the rollup recomputes against the wrong work_date.
- **Fix:** Persist the resolved timezone with each daily_attendance row (new column tz_offset_minutes), so close_day/recompute can reject a date whose underlying events fall outside the recorded local-day window. Add a startup-time sanity check that compares time.time() against an NTP server (or against the DB's now()) and refuses to start if the skew exceeds 5 minutes. Document Asia/Kolkata as the only supported timezone in README.
- **Effort:** MEDIUM

### P1.29 [DATA_INTEGRITY] daily_attendance upsert is race-unsafe under concurrent camera workers
- **File:** `backend/app/repositories/daily_attendance_repo.py:upsert_for_day lines 24-35`
- **Issue:** upsert_for_day does SELECT-then-INSERT in the same Python session. With 4-8 camera workers each owning their own session, two workers can race at the first event of a new day (or at exactly 00:00:00 IST when one worker still has an old day cached) and both attempt to INSERT (employee_id, work_date). The unique constraint uq_daily_attendance_employee_date will make one INSERT raise IntegrityError, which propagates up through AttendanceService.process_auto_event → camera worker's outer try/except → cooldown reset, and the event is silently dropped.
- **Fix:** Replace with PostgreSQL's ON CONFLICT DO NOTHING upsert: `from sqlalchemy.dialects.postgresql import insert as pg_insert; stmt = pg_insert(DailyAttendance).values(...).on_conflict_do_nothing(index_elements=['employee_id', 'work_date']); db.execute(stmt); return self.get_for_day(...)`. Alternatively wrap the existing logic with a SAVEPOINT and catch IntegrityError to fall back to a SELECT.
- **Effort:** SMALL

### P1.30 [RELIABILITY] Embedding cache crashes silently on dim mismatch from new InsightFace versions
- **File:** `backend/app/services/embedding_cache.py:_unpack line 33 and RecognitionService.match line 38`
- **Issue:** EmbeddingCache._unpack rejects vectors whose size != stored dim, but tolerates a mix of 512-d (old) and (say) 511-d / 1024-d (after an InsightFace model upgrade) by warning and skipping. Critical: if the live InsightFace pipeline starts producing vectors of a different dim than what's already in the DB (e.g. operator switched FACE_MODEL_NAME from buffalo_l to buffalo_s, or upstream upgraded the package), the cache silently drops every employee, RecognitionService.match returns None for everyone, and every camera worker reports unknowns. Conversely, training a new image at the new dim works — and the next cache reload mixes dims and crashes np.vstack with a 'vstack expects same shape' ValueError that propagates from load_from_db.
- **Fix:** Introduce a Setting (or env var) FACE_EMBEDDING_DIM with a startup-time assertion that `FaceService().detect(test_image)[0].embedding.size == FACE_EMBEDDING_DIM`. Refuse to start if mismatched. Also, store dim on every embedding row (already done) but add a CHECK constraint or repo-level validation that rejects writes whose dim != settings FACE_EMBEDDING_DIM. Add a separate /api/v1/admin/health/face-model endpoint that returns the live model's vector dim so operators can verify it matches the DB.
- **Effort:** SMALL

### P1.31 [DEPLOYMENT_OPS] No native Postgres enum migration for adding values; downgrade leaks types
- **File:** `backend/migrations/versions/0005_unknown_faces.py:downgrade lines 254-295`
- **Issue:** 0005 explicitly drops `unknown_capture_status` and `unknown_cluster_status` types on downgrade with DROP TYPE IF EXISTS — good. But 0001's downgrade also drops admin_role/camera_type/event_type/session_status (line 308-311) using SQLAlchemy's Enum.drop helper, which is unreliable in some Postgres + SQLAlchemy 2 combos. More importantly: there is no documented or coded pattern for adding a value to an existing enum (e.g. adding HALF_DAY to session_status or a new event type). Postgres `ALTER TYPE … ADD VALUE` cannot run inside a transaction (alembic default), so the migration must use `op.get_context().autocommit_block()`.
- **Fix:** Add a documented helper `add_enum_value(enum_name, value)` in migrations/_helpers.py that wraps `with op.get_context().autocommit_block(): op.execute(...)`. Update CONTRIBUTING/README to require enum changes go through this helper. Replace the 0001 downgrade Enum.drop calls with explicit `op.execute('DROP TYPE IF EXISTS <name>')` to match 0005's style.
- **Effort:** SMALL

### P1.32 [FRONTEND_RESILIENCE] ImageDropzone revokes blob URLs on every state change — orphans visible thumbnails
- **File:** `frontend/components/training/image-dropzone.tsx:lines 38-42 (useEffect cleanup) combined with addFiles at line 44-61`
- **Issue:** The cleanup function `for (const f of files) URL.revokeObjectURL(f.url)` runs on every change to `files` because `files` is the dependency. React runs the cleanup of the previous render BEFORE applying the new effect — meaning when you call `setFiles([...prev, ...next])`, the cleanup revokes ALL URLs from the prior `files` snapshot (the closure captured them), which includes URLs that are still in `combined.slice(0, max)` and still rendered in the `<img src={f.url}>` grid. After the next render the thumbnails point at revoked URLs.
- **Fix:** Track URLs in a `useRef<Set<string>>` and only revoke on actual file removal (already done in `removeAt`) and on unmount via an empty-dep effect: `useEffect(() => () => { urlsRef.current.forEach(URL.revokeObjectURL) }, [])`. Don't put `files` in the cleanup-effect dep array.
- **Effort:** SMALL

### P1.33 [PERFORMANCE] Camera preview poll runs at 600 ms even when card is offscreen or tab is hidden
- **File:** `frontend/lib/hooks/use-cameras.ts:lines 149-204 (useCameraPreview)`
- **Issue:** The preview hook starts a `window.setInterval` at 600 ms regardless of whether the camera tile is in the viewport, whether the tab is the active tab, or whether the browser is minimized. On the Live View page with 4–8 cameras (`frontend/app/(dashboard)/live/page.tsx`), this fires 6.6–13.3 requests/sec into the API non-stop. There's no `IntersectionObserver` to pause offscreen tiles and no `document.visibilitychange` listener. Verified: `grep visibilitychange|document.hidden|refetchIntervalInBackground` returns no hits in the entire frontend.
- **Fix:** Wrap the interval in `IntersectionObserver` so offscreen tiles pause, and listen to `document.visibilitychange` to pause when `document.hidden`. Restart immediately on visibility return. Also reuse TanStack Query's `refetchIntervalInBackground: false` for the dashboard/presence polls (`use-dashboard.ts`, `use-presence.ts`, `use-attendance.ts useEventList`).
- **Effort:** MEDIUM

### P1.34 [DATA_INTEGRITY] All times rendered in browser timezone — drifts from server timezone
- **File:** `frontend/components/attendance/event-table.tsx:line 40-50 fmt() — also: snapshots/snapshot-viewer.tsx, dashboard/timeline-feed.tsx, snapshots/snapshot-card.tsx, presence/presence-table.tsx, settings/settings-form.tsx`
- **Issue:** Every component uses `date-fns format(parseISO(iso))` without an explicit timezone, which renders in the browser's local TZ. The backend stores attendance in a configured timezone (likely Asia/Kolkata). If an admin VPNs from a different timezone (a manager travels to Dubai, a remote support engineer logs in from US) or has a misconfigured Windows clock, the times shown in tables, reports preview, and Recompute dialogs differ from what the server computed. `Reports` page mentions "All exports respect the selected timezone" but the on-screen UI does not. Verified: `grep timezone|timeZone` returned 0 hits in app code.
- **Fix:** Surface server's `system.timezone` setting through `/settings` and store it in AuthContext. Switch all date-fns calls to `date-fns-tz`'s `formatInTimeZone(iso, settings.timezone, '...')`. Show a banner if `Intl.DateTimeFormat().resolvedOptions().timeZone` differs from server TZ.
- **Effort:** MEDIUM

### P1.35 [FRONTEND_RESILIENCE] Report download will time out at 20s and silently fail for large XLSX
- **File:** `frontend/lib/api/reports.ts:lines 3-21 (downloadBlob)`
- **Issue:** `reportsApi.daily/monthly/dateRange/employee` all go through `api.get<Blob>(path, { responseType: 'blob' })` without overriding `timeout`. The default is 20s (`lib/api/client.ts` line 40). A monthly report for 300 employees crossed with 31 days yields a multi-MB XLSX; with 8 cameras of unknown snapshots the date-range export can easily exceed 50 MB. On a slow LAN to the AI PC or under InsightFace CPU contention, the download exceeds 20s and the axios call rejects with `ECONNABORTED` — the user sees `toast.error('Request timed out')` but the server may have actually generated the file successfully (with no resume option).
- **Fix:** Override timeout for blob downloads — `api.get<Blob>(path, { params, responseType: 'blob', timeout: 600_000 })`. Better: switch to streaming via `fetch` + `ReadableStream` with a `Content-Length`-driven progress bar shown in a sticky toast. Even better, use a server-side job-queue pattern: POST to start, poll status, GET the result by ID.
- **Effort:** MEDIUM

### P1.36 [FRONTEND_RESILIENCE] Training upload uses default 20s timeout with no progress, no resume
- **File:** `frontend/lib/api/training.ts:lines 13-21 (upload)`
- **Issue:** The face-image upload `trainingApi.upload` POSTs `multipart/form-data` containing up to 100 images of up to 10 MB each (verified in `components/training/image-dropzone.tsx` MAX_SIZE_MB=10) — total 1 GB — through `api.post` with the default 20s timeout. There's no `onUploadProgress` handler, no chunked/resumable upload, and InsightFace runs synchronously per image on the server which makes 100 images take >20s easily.
- **Fix:** Pass `onUploadProgress` via axios config from `api.post`, surface progress in `ImageDropzone`. Set `timeout: 0` (no client timeout) for uploads since the server side has its own. Long-term: split into per-file requests with a progress bar and retry-on-failure for failed files only.
- **Effort:** MEDIUM

### P1.37 [FRONTEND_RESILIENCE] No role-based UI gating — VIEWER sees all admin actions, gets 403 on click
- **File:** `frontend/components/layout/sidebar.tsx:lines 25-69 (NAV_ITEMS rendered for all roles); also camera-table.tsx Edit/Delete dropdown, employee-table.tsx, settings-form.tsx`
- **Issue:** AuthContext exposes `admin.role` (SUPER_ADMIN | ADMIN | VIEWER) but the only place it's read is `UserMenu` (display only). Grep for `admin.role` returns only that one file. Every nav item, every Edit/Delete button, every Add Camera/Add Employee/Settings form is rendered for VIEWER roles. The backend correctly returns 403, surfaced as a `toast.error(err.message)`.
- **Fix:** Create a `useCan(perm)` hook backed by `admin.role`. Hide destructive nav items and action buttons for VIEWER. Show a read-only banner. Make the settings form `disabled` for non-SUPER_ADMIN. Same for camera Add/Edit/Restart/Delete.
- **Effort:** MEDIUM

### P1.38 [DATA_INTEGRITY] Embedding cache rebuild reads uncommitted writes (stale)
- **File:** `backend/app/services/training_service.py:lines 134-136, 209-211, 272-273, 302-303 (and embedding_cache.py:42-43)`
- **Issue:** `TrainingService.enroll`, `capture_and_enroll`, `auto_enroll_from_frame`, and `delete_image` all call `self.cache.load_from_db()` immediately after `self.db.flush()` but BEFORE the outer transaction commits. `EmbeddingCache.load_from_db()` opens a SEPARATE `session_scope()` (its own connection). Under PostgreSQL READ COMMITTED isolation (the default), that second connection cannot see the flushed-but-uncommitted rows. The cache rebuild therefore silently misses the very embedding that triggered the rebuild.
- **Fix:** Move the cache rebuild to happen AFTER the outer transaction commits. Either (a) accept that the API handler controls rebuild — call `cache.load_from_db()` after the request finishes (FastAPI background task), or (b) inside the existing session, refresh the cache from `self.db` rather than opening a fresh session, or (c) call `self.db.commit()` before rebuild (loses atomicity of the larger request). Option (a) is cleanest.
- **Effort:** SMALL

### P1.39 [DATA_INTEGRITY] Snapshot/training JPEG written before DB commit — orphan file on rollback
- **File:** `backend/app/services/attendance_service.py:process_auto_event lines 76-93; training_service.py _persist_face lines 326-353`
- **Issue:** `save_event_snapshot` writes the JPEG to disk THEN the DB row is added and the transaction is committed (or rolled back). If anything between the write and the commit fails — DB pool exhausted, Postgres restart mid-transaction, daily-rollup recompute raising, OS reboot/power loss — the file is left on disk with no DB row pointing at it. Symmetric in `_persist_face`: image is written to `TRAINING_DIR` before the EmployeeFaceImage row is flushed/committed.
- **Fix:** Generate the path + bytes in memory first; insert the DB row + flush; only AFTER commit write the bytes to disk (use SQLAlchemy `after_commit` event or write inside a `try` that schedules deletion if the transaction fails). For the orphan-on-disk case, add a startup janitor or weekly job that scans `SNAPSHOT_DIR` / `TRAINING_DIR` for files that no DB row references.
- **Effort:** MEDIUM

### P1.40 [RELIABILITY] No SIGTERM/SIGINT signal handler — workers never join on Windows kill
- **File:** `backend/app/main.py:lifespan handler, lines 23-53`
- **Issue:** Lifespan's `finally` runs `camera_manager.stop_all()` + `dispose_engine()` only when uvicorn shuts down cleanly. On Windows there's no SIGTERM; Ctrl-C in the terminal does work via KeyboardInterrupt but `taskkill /F`, a service-controller stop, or a power loss bypasses lifespan entirely. The 4-8 RTSP threads are daemons, but the JPEG writes / DB commits in flight inside camera workers can be killed mid-write, leaving partial JPEGs or uncommitted snapshot files. There is no `signal.signal(SIGTERM, ...)` and no Windows ServiceCtrlHandler. The codebase also has no `signal.` import anywhere in `backend/`.
- **Fix:** Install a process supervisor: ship with NSSM or a real Windows Service wrapper that translates the service-stop signal into a clean shutdown trigger (write a stop-flag file the app polls, or use a properly-installed signal handler on the main thread that calls `camera_manager.stop_all()`). Add `signal.signal(SIGINT, ...)` and `signal.signal(SIGTERM, ...)` in `create_app` for the *nix case. Document the supervisor install as required for production deployments.
- **Effort:** MEDIUM

### P1.41 [SECURITY] No login rate limit — JWT brute force / credential stuffing open
- **File:** `backend/app/api/v1/auth.py:login endpoint, lines 20-26`
- **Issue:** `POST /api/v1/auth/login` has no throttling, no lockout after N bad attempts, and no audit log. With bcrypt costs verifying in ~100ms, an attacker on the LAN (the cameras are on 192.168.1.x, but admin laptops are too) can try 10/sec until they guess. There is no `failed_login_count` field on the Admin model. No `AuditLog` table exists in `backend/app/models/`.
- **Fix:** Add a per-username in-memory throttle (slowapi or hand-rolled): after 5 failed attempts, return 429 for 5 minutes; after 20 failures in an hour, lock the account until an admin unlocks it. Add an `audit_log` table tracking: login success/failure, password change, settings change, employee delete, camera CRUD, promote-cluster-to-employee. Cheap to implement, huge for ops + DPDP compliance.
- **Effort:** MEDIUM

### P1.42 [PRIVACY_COMPLIANCE] No biometric retention/consent — DPDP Act 2023 non-compliance
- **File:** `backend/app/services:n/a — entire stack`
- **Issue:** Embeddings (`employee_face_embedding.vector`), snapshots, and training images persist forever for active employees; only the unknowns pipeline has a retention setting. On employee termination (`Employee.is_active=False`), embeddings and snapshots are NOT deleted — they stay queryable in the DB and on disk indefinitely. There is no consent record, no employee-facing deletion endpoint, no biometric-data export, no admin notification of who-accessed-what. India's Digital Personal Data Protection Act 2023 treats face embeddings as personal data and requires consent, purpose limitation, retention bounds, and a right to erasure.
- **Fix:** Add `Employee.consent_signed_at` + a deletion cascade in `EmployeeRepository.soft_delete` that hard-deletes embeddings, training images, and snapshots after a configurable grace period (default 30 days). Add an admin endpoint `DELETE /employees/{id}/biometrics` that purges everything but keeps the audit row. Add a banner in the UI showing the retention policy. Capture admin-id on every read of training images / face vectors in the audit log.
- **Effort:** LARGE

### P1.43 [PERFORMANCE] DB pool capped at 20 connections — exhausted under load
- **File:** `backend/app/db/session.py:_build_engine, lines 17-26`
- **Issue:** `pool_size=10, max_overflow=10` → hard max 20 simultaneous DB connections. Each of the 4-8 camera workers regularly takes a connection (one per detected face for the auto-enroll, snapshot, attendance, daily-rollup chain). The unknowns capture pipeline takes another. The settings/embedding cache rebuilds take more. Plus FastAPI request handlers. A burst of recognitions at 9 AM (everyone arrives at once) can saturate 20 connections, and the next worker waits up to 30s on `cv2.read` heartbeat before being declared 'wedged' by the health loop. There is no `pool_timeout` set, so it defaults to 30s and may stall request handlers indefinitely.
- **Fix:** Increase `pool_size=20, max_overflow=30, pool_timeout=10`. Add a quick metric: log when `engine.pool.checkedout()` exceeds 80% of capacity. Better: hold ONE long-lived session per camera worker thread (scoped_session) and use `db.begin_nested()` / `db.rollback()` per event — avoids constant connect/release churn.
- **Effort:** SMALL

### P1.44 [EDGE_CASES] Disk-full causes silent attendance loss
- **File:** `backend/app/utils/image_utils.py:write_jpeg lines 17-22, called from SnapshotService.save_event_snapshot`
- **Issue:** `write_jpeg` raises `RuntimeError`/`OSError` (ENOSPC, EACCES) when the disk is full or read-only. The exception bubbles up into `AttendanceService.process_auto_event`, then up to the camera_worker outer `except Exception`, which only stores `last_error` and continues. So when disk fills, every detected face fails the snapshot write, no event is recorded, no daily rollup ticks, but the worker keeps running and reading frames — looks healthy in `/cameras/health`. There is no free-space monitor and no purge-on-fill failsafe.
- **Fix:** At startup and every hour, log + emit a metric for `shutil.disk_usage(STORAGE_ROOT).free`. When <10% free, auto-trigger the snapshot purge with a more aggressive cutoff; when <2% free, send an admin alert (email/webhook) and switch SnapshotService into a 'log-only' mode where events are still recorded but snapshot_path stays NULL. Add a scheduled (nightly) `SnapshotService.purge_before(today - retention_days)` so manual triggering isn't required.
- **Effort:** MEDIUM

### P1.45 [DATA_INTEGRITY] Daily rollup recompute races with close_day on midnight boundary
- **File:** `backend/app/services/daily_attendance_service.py:recompute, close_day, recompute_range — no row-level locking`
- **Issue:** `DailyAttendanceRepository.upsert_for_day` then mutates `row.in_time`, etc., and `flush()`. If a camera worker creates an event at 23:59:59 that triggers `recompute(employee_id, yesterday)` while an admin clicks 'Close Day' for yesterday at the same instant, both transactions read the same `daily_attendance` row, both mutate, last writer wins. There's no `SELECT ... FOR UPDATE`, no version/etag, and `is_day_closed` could be set then immediately overwritten with stale data from the slower transaction.
- **Fix:** Add a unique constraint `(employee_id, work_date)` on `daily_attendance` (probably already exists — verify). Inside `recompute` and `close_day`, do `db.execute(select(DailyAttendance).where(...).with_for_update())` before mutating. Or use SQLAlchemy `version_id_col` on the model for optimistic concurrency.
- **Effort:** MEDIUM

### P1.46 [DATA_INTEGRITY] HDBSCAN recluster races with concurrent capture writes
- **File:** `backend/app/services/unknown_recluster_service.py:run() lines 113-275`
- **Issue:** Recluster reads all KEEP captures (`list_keep_in_pending_clusters`), runs HDBSCAN, then migrates cluster_id values. Meanwhile a camera worker may insert a new capture for one of the clusters being merged into MERGED — the new capture references a cluster that's about to be marked MERGED (with no member_count, centroid stale), or it may pass cluster matching against a centroid that the recluster is concurrently rewriting. No DB-level lock on `unknown_face_cluster` rows during recluster.
- **Fix:** Take a process-wide lock (`threading.Lock`) shared between `UnknownReclusterService.run` and `UnknownCaptureService.maybe_capture` so they cannot run simultaneously. Alternative: do recluster inside a `SELECT ... FOR UPDATE` over all PENDING clusters, but that blocks captures for the duration (could be many seconds). The shared-lock approach is simpler.
- **Effort:** SMALL

### P1.47 [SECURITY] Bootstrap admin password never expires; no forced rotation
- **File:** `backend/app/services/auth_service.py:bootstrap_admin lines 70-86; Admin model has no password_changed_at`
- **Issue:** On first boot the bootstrap admin is created from `BOOTSTRAP_ADMIN_PASSWORD`. The log warning says 'change the password immediately' but the system does not force this. There's no `must_change_password` flag, no expiry, no admin model field for `password_changed_at`. An operator who deploys and forgets keeps `ChangeMe@123` indefinitely.
- **Fix:** Add `must_change_password` (bool, default True for bootstrap admin) on `Admin`. Have the `/auth/login` flow return a flag that the frontend uses to force the password-change screen before allowing any other action. Optionally enforce 90-day rotation at the policy layer.
- **Effort:** SMALL

### P1.48 [FRONTEND_SECURITY] JWT in JS-readable cookie + no CSP = XSS = full account theft
- **File:** `frontend/lib/auth/session.ts:lines 11-17 (setToken)`
- **Issue:** The JWT is written to cookie `aa_token` without HttpOnly (intentionally, so the SPA can read it via js-cookie and inject `Authorization: Bearer ...`). There is also no Content-Security-Policy header anywhere in the Next config or backend, and Secure flag is only set in `production` (so over plain HTTP on-LAN deployments it's never Secure). A single XSS sink anywhere in the dashboard (a future markdown/notes field, a dependency supply-chain attack on the 100+ npm packages, or a reflected payload via the `next` query param) immediately ex-filtrates the SUPER_ADMIN token to an attacker for 24 hours.
- **Fix:** Move to HttpOnly+Secure+SameSite=Strict cookies. Set the cookie server-side from the `/auth/login` response (FastAPI `response.set_cookie(httponly=True, samesite='strict', secure=True)`) and switch the axios client to `withCredentials: true` instead of injecting the Authorization header. Also add a strict CSP via `next.config.mjs` headers() (default-src 'self', no inline scripts/styles except hashed). This kills the XSS-to-token-theft chain.
- **Effort:** MEDIUM

### P1.49 [FRONTEND_SECURITY] Open redirect via `?next=` param after login
- **File:** `frontend/components/auth/login-form.tsx:lines 32-34, 56 (nextPath, window.location.assign)`
- **Issue:** `rawNext` comes straight from `searchParams.get("next")` and is passed to `window.location.assign(nextPath)` with no validation that it's a same-origin relative path. `/login?next=https://attacker.example/phish` redirects the freshly-authenticated admin off-site (where the attacker can show a fake re-login page to harvest credentials). Same for `next=javascript:...` in some browser combos — `window.location.assign` will execute the URL as given.
- **Fix:** Sanitize `nextPath` before navigation: require it to start with `/` and NOT start with `//` or `/\`. Reject any value that fails that check and fall back to `/dashboard`. Same guard belongs in `middleware.ts` line 23 where `next=pathname` is set (pathname is safe but anything could arrive via direct URL crafting).
- **Effort:** SMALL

### P1.50 [FRONTEND_SECURITY] Middleware never validates JWT expiry — expired token still passes
- **File:** `frontend/middleware.ts:lines 9-27`
- **Issue:** Middleware only checks `req.cookies.get(TOKEN_COOKIE_NAME)?.value` for presence. The js-cookie write in `session.ts` uses `expires: TOKEN_EXPIRES_DAYS` (default 1 day) but the JWT itself encodes `exp` separately (JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440 backend default). If the backend admin shortens token TTL but the frontend `TOKEN_EXPIRES_DAYS` is unchanged, the cookie lives longer than the token. Worse, anyone who copies a stale-but-not-expired cookie value gets straight through middleware to /dashboard; only the eventual `/auth/me` round-trip in AuthProvider catches it (and during that round-trip the dashboard layout renders briefly).
- **Fix:** Either (a) decode the JWT in middleware with `jose` and check exp/signature against `process.env.JWT_SECRET_KEY`, or (b) make middleware call `/auth/me` server-side with the cookie attached and trust only that. Option (a) is cheap and keeps middleware on the edge runtime.
- **Effort:** MEDIUM

### P1.51 [SECURITY] No server-side logout — token remains valid until exp
- **File:** `frontend/lib/auth/context.tsx:lines 67-71 (logout)`
- **Issue:** Logout only does `clearToken()` + `router.replace('/login')`. There is no `/auth/logout` endpoint on the backend (confirmed: only `/login`, `/me`, `/change-password` exist in `backend/app/api/v1/auth.py`). The JWT remains cryptographically valid for up to 1440 minutes after logout. If the token leaked (browser history, clipboard, screen share, browser sync to a personal device) before logout, logging out does literally nothing — the attacker can keep using it.
- **Fix:** Add a `jti` claim to issued tokens, persist a `revoked_jti` table (or Redis set if you have it; otherwise just a small Postgres table with `expires_at` for self-cleanup). On logout, POST `/auth/logout` which inserts the jti into the revoke list. `decode_token` checks revoke list. Also revoke automatically on change-password. Minimum effort version: a `tokens_invalidated_before` column on admin, bumped on logout — invalidates ALL of that admin's sessions, simpler to implement.
- **Effort:** MEDIUM

### P1.52 [SECURITY] Default bootstrap password is never required to be rotated
- **File:** `backend/app/services/auth_service.py:lines 70-86 (bootstrap_admin) and Admin model`
- **Issue:** Bootstrap seeds the SUPER_ADMIN with `BOOTSTRAP_ADMIN_PASSWORD` (today `ChangeMe@123`) and logs a warning. There is no `must_change_password` flag on the Admin model, no first-login forced password change in the frontend, and no policy check that prevents login with the literal seed password forever. An on-prem deployment that doesn't reset is one nmap-scan + `admin:ChangeMe@123` away from total compromise. The frontend has NO change-password UI at all (grep for `ChangePassword` returned only the API client definition and the type — no page or dialog uses it).
- **Fix:** Add `must_change_password BOOLEAN DEFAULT FALSE` column. Set it TRUE in `bootstrap_admin()`. After login, if true, AuthProvider redirects to a forced /change-password page and blocks every other route until it's done. Also build the change-password dialog in the user menu (the backend endpoint already exists at `/auth/change-password`). Reject `BOOTSTRAP_ADMIN_PASSWORD` as a valid new password too.
- **Effort:** MEDIUM

### P1.53 [SECURITY] No login rate limiting — brute force the admin password trivially
- **File:** `backend/app/api/v1/auth.py:lines 20-26 (login endpoint)`
- **Issue:** The login endpoint has zero rate limiting, no failed-attempt tracking, no account lockout, and no CAPTCHA. With bcrypt hashing it takes a few hundred ms per attempt, but that still allows ~10/sec or ~860k/day per attacker thread. The bootstrap admin username is fixed (`admin` by default per BOOTSTRAP_ADMIN_USERNAME), so the attacker only needs to guess the password. There's no logging of failed attempts either (`AuthenticationError` is raised before any audit log entry).
- **Fix:** Add slowapi or a simple in-process per-IP+username rate limit (e.g. 5 attempts per 5 min per username, 20 per IP per 5 min) on `/auth/login`. Add `failed_login_count` + `locked_until` columns on Admin and lock for 15 min after 10 failures. Log each failure with username + IP via `log.warning` so operators see it.
- **Effort:** MEDIUM

### P1.54 [DEPLOYMENT_OPS] No forgot-password / SUPER_ADMIN recovery path
- **File:** `backend/app/services/auth_service.py:file-wide (no reset method)`
- **Issue:** There is no `/auth/forgot-password` endpoint, no email-based reset, and no "second SUPER_ADMIN unlocks the first" flow. The only path to reset a forgotten password is direct DB access (UPDATE admins SET password_hash = ...) or re-running `bootstrap_admin()` which is a no-op once any admin exists (count > 0 returns early). If the single SUPER_ADMIN forgets their password and there are no other admins, the system is unrecoverable without DBA intervention.
- **Fix:** Ship a CLI command (e.g. `python -m app.cli reset-admin-password --username admin`) that asks for a new password via stdin and updates the row. Document it in the runbook. Optionally, allow `bootstrap_admin()` to also act as `ensure_admin_exists()` — if zero ACTIVE super-admins exist, recreate with bootstrap creds and log loudly. This avoids "single point of permanent failure" without needing SMTP.
- **Effort:** SMALL

### P1.55 [PRIVACY_COMPLIANCE] No audit trail of who viewed which employee's snapshots/face data
- **File:** `backend/app/api/v1/snapshots.py:lines 85-99 (get_event_snapshot), all of unknowns.py`
- **Issue:** GET /snapshots/by-event/{id}, GET /unknowns/captures/{id}/image, GET /employees/{id}/training/images return face images of identifiable individuals and are NOT logged anywhere except the generic uvicorn.access log (which logger.py explicitly turns DOWN to WARNING level — line 44). No PII-access middleware exists. A malicious or compromised ADMIN can paginate through every employee's snapshots and there is no record.
- **Fix:** Add a `pii_access_log` table (id, admin_id, subject_employee_id, resource_type, resource_id, endpoint, ts). Wrap snapshot, training-image, and unknown-capture GETs with a middleware/decorator that inserts a row before returning the FileResponse. Add an admin-only GET /admin/pii-access-log?employee_id=X for subject access requests.
- **Effort:** MEDIUM

### P1.56 [PRIVACY_COMPLIANCE] RTSP URL with embedded camera credentials leaks to every authenticated user
- **File:** `backend/app/schemas/camera.py:CameraRead schema lines 133-143; cameras.py list_cameras line 43-48`
- **Issue:** GET /api/v1/cameras returns `rtsp_url` verbatim — and `_sanitize_rtsp_url` actually encodes the password INTO the URL (`user:password@host`). Any authenticated admin (including future VIEWER scope expansions) sees the unmasked camera password. This is also written to JSON responses, browser DevTools, and any HTTP access log on the wire. Camera passwords are credentials to physical security infrastructure.
- **Fix:** Store `rtsp_url` split into (host, port, username, password_encrypted_with_app_key, path). In CameraRead, return only host:port/path and a boolean `has_credentials`. Provide a separate SUPER_ADMIN-only GET /cameras/{id}/credentials that returns the password and writes an audit log entry.
- **Effort:** MEDIUM

### P1.57 [PRIVACY_COMPLIANCE] Absolute filesystem paths leak in API responses (storage layout disclosure)
- **File:** `backend/app/schemas/training.py:FaceImageRead.file_path (line 13), UnknownCaptureRead.file_path (schemas/unknowns.py line 19), AttendanceEventRead.snapshot_path (schemas/attendance.py line 18)`
- **Issue:** Three Read schemas serialize the absolute on-disk path to the API consumer: `./storage/training_images/EMP001/uuid.jpg`, `./storage/unknowns/cluster_42/xyz.jpg`, `./storage/snapshots/2026-06-06/17/170230_IN_ab12.jpg`. These paths reveal the server's directory layout, the storage volume, the employee_code-to-folder mapping, and (for snapshots) the precise capture time + event_type even when the consumer is not authorized to view the JPG itself. They are also written to browser localStorage/devtools and uvicorn access logs.
- **Fix:** Replace `file_path: str` with `image_url: str` in the Read schemas, where the URL is a opaque `/api/v1/...{id}/image` endpoint already gated by RBAC. Strip the raw path from JSON responses. Update the frontend to use the URL form.
- **Effort:** SMALL

### P1.58 [PRIVACY_COMPLIANCE] No retention policy or auto-purge for snapshots or employee face images
- **File:** `backend/app/services/snapshot_service.py:purge_before (line 116) — manual only; no scheduler`
- **Issue:** UnknownFaceCluster has `unknown_retention_days` (default 30) but there is NO equivalent for: (a) employee face_images (kept until /employees/{id}/erase, which doesn't exist), (b) snapshot JPGs under storage/snapshots/* (only purged when an admin manually calls DELETE /snapshots/purge with a date), (c) attendance_events themselves. Even the unknown purge is not scheduled — it requires somebody to POST /unknowns/purge.
- **Fix:** Add `snapshot_retention_days` to attendance_settings (sensible default 180). Add an APScheduler job (or Windows Task Scheduler stub in docs) that runs daily at 03:00 and calls SnapshotService().purge_before(today - retention_days) + UnknownPurgeService().purge(). Log the outcome to a `retention_job_log` table.
- **Effort:** MEDIUM

### P1.59 [PRIVACY_COMPLIANCE] No database backups configured — biometric data has zero disaster recovery
- **File:** `DEPLOYMENT:README + repo (no pg_dump script, no backup doc)`
- **Issue:** Repo has no pg_dump cron, no Windows scheduled-task example, no offsite-backup config, no encrypted-backup pattern, no restore runbook. DPDP S.8(4) requires the fiduciary to take steps including 'backups' to ensure data availability. A bad PostgreSQL upgrade or disk-failure event wipes years of attendance + biometric data — the operator then has no record of consent, no record of who-was-an-employee, and no ability to restore.
- **Fix:** Ship `backend/scripts/backup_db.ps1` that runs `pg_dump --format=custom --no-owner | gpg --encrypt --recipient OPERATOR > backup_$(date).pgc.gpg`, schedule daily via Windows Task Scheduler. Document an offline external-drive rotation. Include a `restore_db.ps1` and a tested restore drill in the SOP.
- **Effort:** MEDIUM

### P1.60 [PRIVACY_COMPLIANCE] No documented breach notification runbook (72-hour DPDP requirement)
- **File:** `DEPLOYMENT:README.md, no docs/INCIDENT_RESPONSE.md`
- **Issue:** DPDP S.8(6) requires the data fiduciary to notify the Data Protection Board AND affected data principals 'in such form and manner as may be prescribed' on a personal-data breach. The MeitY draft rules expect notification 'without undue delay' typically interpreted as within 72 hours. The repo has no incident-response runbook, no DPB contact template, no breach-scope-assessment checklist, and no list of which DB tables/files contain PII (so the operator can quickly answer 'what was exposed').
- **Fix:** Add docs/INCIDENT_RESPONSE.md with: (a) PII inventory (which tables/files), (b) 72-hour timeline with concrete steps (0-2h: triage, 2-24h: scope, 24-48h: draft notification, 48-72h: file with DPB), (c) draft notification email template in English + Hindi, (d) chain-of-custody instructions for evidence, (e) DPB filing portal link. Have the operator sign-off that they read it during install.
- **Effort:** MEDIUM

### P1.61 [PRIVACY_COMPLIANCE] No encryption-at-rest enforcement or even a doc gate flagging the risk
- **File:** `DEPLOYMENT:README.md, .env.example`
- **Issue:** PostgreSQL data dir, the entire ./storage tree (face images, embeddings written through bytea but on disk in PG, snapshots, unknown captures, model files), and rotating logs at ./logs/app.log (which contain the absolute file_paths of snapshots — see logger format on line 22-25 of logger.py) are all written to whatever Windows volume the operator chose. There is no documented requirement for BitLocker, no install-time check, no .env knob like REQUIRE_DISK_ENCRYPTION_ACK=true.
- **Fix:** Add a section to README.md 'Operator obligations: BitLocker' that requires the install drive to have BitLocker enabled before going live. Add a startup probe (PowerShell `Get-BitLockerVolume` for the storage drive) that logs a critical warning if encryption is off, and a config flag `OPERATOR_ACK_DISK_ENCRYPTION=true` that must be set after acknowledgement.
- **Effort:** SMALL

### P1.62 [DATA_INTEGRITY] Snapshot is written to disk before DB commit — orphans and missing events on crash
- **File:** `backend/app/services/attendance_service.py:process_auto_event:76-93`
- **Issue:** `save_event_snapshot` writes the JPEG synchronously to disk, THEN the AttendanceEvent row is added. If the process is killed (power loss, BSOD, OOM) between line 76 and the implicit commit at end of `session_scope`, the JPEG sits orphaned. If `write_jpeg` raises mid-write (disk full), `event_repo.add` is never called — the attendance event silently does not exist, but the cooldown was already consumed upstream in the worker. `write_jpeg` (utils/image_utils.py:17-22) uses `path.write_bytes(buf.tobytes())` directly to the final path, not write-to-temp-then-rename, so a power failure during the write leaves a half-written truncated JPEG that the admin UI later renders as a broken image.
- **Fix:** Switch `write_jpeg` to atomic write: write to `path.with_suffix('.jpg.tmp')`, fsync, `os.replace` to final path. Reorder `process_auto_event` to commit the DB row first with `snapshot_path=None`, then write the file, then UPDATE the row's snapshot_path — so on crash the worst outcome is a missing image, not a missing event.
- **Effort:** SMALL

### P1.63 [SECURITY] No login rate limiting / lockout — brute-force trivial
- **File:** `backend/app/api/v1/auth.py:login:20-26`
- **Issue:** `POST /auth/login` has zero rate limiting, no IP throttling, no account lockout on N consecutive failed attempts, no captcha. The auth_service does not record failed-login counts. There is no slowapi / no fastapi-limiter dependency. With a single admin account (because there is no way to create more — see other finding) on the office LAN with credentials hashed by bcrypt at default cost, an attacker on the same Wi-Fi can run a 10k password dictionary against it in seconds.
- **Fix:** Add a `failed_login_attempts` column + `locked_until` to admins table. After 5 failed attempts in 15 minutes, set locked_until = now + 15 min and reject `verify_password` calls until then. Add slowapi rate-limit of 10/min per IP on `/auth/login`. Log every failed attempt (loud — see audit-log finding).
- **Effort:** SMALL

### P1.64 [PRIVACY_COMPLIANCE] No audit log of admin actions — biometric data tampering invisible
- **File:** `backend/app/models:no audit_log model exists — grep for AuditLog/audit_trail returns nothing`
- **Issue:** Under India DPDP Act 2023, employer-collected biometric data is sensitive personal data. The Act requires the data fiduciary to maintain reasonable security safeguards and accountability records. This system records `last_login_at` on the admins table and `corrected_by` on manually-edited events, but does NOT record: login attempts (success or failure), employee enrollment / deletion, employee deactivation, snapshot/embedding deletion, configuration changes (face_match_threshold, cooldown), password changes by user, or admin role changes (would be moot — no such endpoint exists). When something is wrong six months later there is no answer to 'who did this'.
- **Fix:** Add `audit_log` table (id, actor_admin_id, action, target_type, target_id, payload_json, ip_address, user_agent, created_at). Write a thin `AuditLogService.record(...)` and call it from every mutating endpoint: login (success/fail), change_password, create/update/delete event, create/delete employee, enroll/replace embeddings, settings update, promote/discard unknown cluster. Retain for at least 5 years.
- **Effort:** MEDIUM

### P1.65 [PRIVACY_COMPLIANCE] No biometric consent record, no retention policy, no DPDP rights endpoints
- **File:** `backend/app/models/employee.py:employee schema — no consent_given_at, no consent_revoked_at, no retention fields`
- **Issue:** DPDP 2023 requires explicit consent for processing sensitive personal data (biometrics qualify), the right to withdraw consent, the right to data erasure, and a defined retention period. The employee model has no `consent_given_at`, `consent_document_path`, `consent_revoked_at`, `data_retention_until` fields. Snapshots, embeddings, and face_images persist indefinitely with no documented purge policy. There is no admin endpoint to fully erase a single employee's biometric data and all derived events (right-to-be-forgotten). When an employee leaves the company, their face embedding remains in the cache and DB forever.
- **Fix:** Add consent fields to employees table + upload-consent-PDF endpoint. Add `POST /employees/{id}/forget` that hard-deletes embeddings, face_images, snapshots (filesystem), and anonymizes events (replace employee_id with NULL or a tombstone). Add a `data_retention_days` setting; nightly job auto-runs forget on employees whose `terminated_at` is older than retention. Publish a privacy policy in the frontend.
- **Effort:** LARGE

### P1.66 [DEPLOYMENT_OPS] No upgrade or rollback procedure documented or scripted
- **File:** `DEPLOYMENT:README.md — no upgrade.md, no rollback.md, no ops/ directory`
- **Issue:** There is no documented upgrade path. The README only describes first-install. There is no script that: (1) takes a pre-upgrade pg_dump + tarball of storage/, (2) git pulls, (3) pip installs requirements diff, (4) runs `alembic upgrade head`, (5) runs `npm install && npm run build`, (6) restarts services, (7) on failure restores from step (1). Alembic has no downgrade tests. The operator currently has zero way to revert a broken release — the only state on the machine is 'latest main'.
- **Fix:** Add `ops/upgrade.ps1` and `ops/rollback.ps1` with the workflow above. Add a `VERSION` file or git tag check. Keep the previous git SHA + previous pg_dump as 'last-known-good'. Document in `OPERATIONS.md`: 'to upgrade, run ops\\upgrade.ps1; to roll back, run ops\\rollback.ps1'. Test the rollback in a staging copy at least once per release.
- **Effort:** MEDIUM

### P1.67 [RELIABILITY] No single-instance lock — accidental dual launch corrupts pipeline
- **File:** `backend/app/main.py:create_app / lifespan (entire file)`
- **Issue:** There is no PID-file, port-lock, or DB-row lock to prevent two uvicorn instances pointing at the same `DATABASE_URL` from starting. Two CameraManagers would each spawn their own thread per camera — each camera worker would open a second RTSP stream to the same camera (some cameras drop the first connection), both would run InsightFace concurrently saturating CPU, both would attempt to create attendance events and create duplicates that bypass the cooldown (cooldown is in-process), and `bootstrap_admin()` has a TOCTOU race that could create two admins.
- **Fix:** Acquire a process-wide lock during lifespan startup: bind a UDP socket on 127.0.0.1:9527 or open a SQL advisory lock (`pg_try_advisory_lock(<constant>)`) on the shared DB. If the lock is already held, log a fatal error and exit. Also switch RotatingFileHandler to `concurrent-log-handler` or write per-PID log files.
- **Effort:** SMALL

### P1.68 [RELIABILITY] Lifespan startup has no error handling — one bad config kills the API
- **File:** `backend/app/main.py:lifespan:24-46`
- **Issue:** Calls `bootstrap_admin()`, `face_service.load()`, `embedding_cache.load_from_db()`, `camera_manager.start_all()` with no try/except. If Postgres is starting slowly on boot (it's a separate service whose readiness Windows does not coordinate with uvicorn), `bootstrap_admin` raises and FastAPI never finishes startup — uvicorn exits. Same for a corrupted InsightFace model file (model loaded from `./storage/models` — `face_service.py:31-54` catches and re-raises as FaceRecognitionError, but the lifespan does not catch it). The exception is logged once and the process is dead until manual restart.
- **Fix:** Add retry-with-backoff around `bootstrap_admin` and `embedding_cache.load_from_db` (up to 60s, retry every 2s) — Postgres may be coming up. Wrap `face_service.load()` and `camera_manager.start_all()` in try/except: if FaceService fails, log critical and let the API still come up in 'degraded' mode (UI shows the model load error and a 'retry' button) — better than no UI at all. Add a model-file checksum verification at load.
- **Effort:** SMALL

### P1.69 [EDGE_CASES] System clock drift will silently shift attendance times — no NTP enforcement
- **File:** `backend/app/utils/time_utils.py:now_utc:15-16 — `datetime.now(tz=timezone.utc)` (Windows wall clock)`
- **Issue:** All event timestamps come from `datetime.now()` — the OS wall clock. Windows 10 syncs with time.windows.com by default, but office firewalls often block 123/UDP; consumer hardware clocks drift several seconds per month and many more after CMOS battery dies. The code monotonic-clocks for cooldowns/health (good) but persists wall-clock for actual events. No startup check that the clock is sane (e.g. within 30s of a known reference) and no logged drift telemetry. A 5-minute drift will mark on-time employees as LATE per the 09:30 grace window. A reverse drift (clock set back) breaks `STATE_TRANSITIONS` ordering and can make event_time < previous event_time within the same day, confusing daily_attendance recompute.
- **Fix:** Document in OPERATIONS.md the exact `w32tm /config /manualpeerlist:pool.ntp.org /syncfromflags:manual /update; w32tm /resync` sequence and verify outbound NTP is allowed by office firewall. At backend startup, fetch one HTTP `Date` header from a reference (Google) and log a CRITICAL warning if delta > 10s. Add a daily background check that compares system time to a reference and writes the delta to `/admin/live-status`.
- **Effort:** SMALL

### P1.70 [OBSERVABILITY] No nightly/scheduled jobs: day-close, retention purge, cluster re-cluster never run
- **File:** `backend/app/main.py:lifespan — no APScheduler, no background job registration`
- **Issue:** Three operations are designed to be scheduled but are never actually scheduled: `DailyAttendanceService.close_day` is only exposed as a manual POST endpoint (api/v1/attendance.py:217) — if the admin forgets to click it, employees who walked out as BREAK_OUT stay BREAK_OUT forever and dashboards lie. `SnapshotService.purge_before` requires a manual API call. `unknown_recluster_service` says 'safe to schedule (e.g. nightly cron)' but nothing schedules it. Once-a-day jobs are reliability work — humans miss them on weekends, on holidays, when the admin is on leave.
- **Fix:** Add APScheduler to lifespan: `close_day(today-1)` at 02:30 daily; `purge_before(today - settings.snapshot_retention_days)` at 03:00 daily; `unknown_recluster.run()` at 03:30 daily; disk-space + clock-drift health probes hourly. Add a `scheduled_jobs` table that records each run's outcome so the UI can show 'last day-close ran 23h ago, status ok'.
- **Effort:** MEDIUM


## P2_NICE_TO_HAVE (44 items)

- **P2.1** [OBSERVABILITY] **Recognition score distribution not collected — threshold tuning is blind** — `backend/app/workers/camera_worker.py` — Every face-detect produces a similarity `match.score`, but only the matched events are persisted (confidence column on AttendanceEvent). Unmatched scores (the ones near the threshold — the ones that w
- **P2.2** [OBSERVABILITY] **Slow camera worker ticks (>2s) not logged** — `backend/app/workers/camera_worker.py` — The worker loop calls reader.read(), face_service.detect(), recognition.match(), session_scope() each tick. There is no timing instrumentation around any of these — a slow tick (>2s = something is wro
- **P2.3** [OBSERVABILITY] **No frontend error sink — JS errors invisible to backend** — `backend/app/api/v1/__init__.py` — The backend has no `/api/v1/client-errors` endpoint to receive frontend exceptions, network failures, or unhandled promise rejections. When the Next.js app crashes on a customer machine, nobody knows 
- **P2.4** [PERFORMANCE] **Recognition matmul rescans all vectors per face per camera** — `backend/app/services/recognition_service.py` — Each `match()` call does `matrix @ q` over every employee vector, then a Python loop building a per-employee dict and sorting. At 8 cameras x 2 FPS detection x 5000 employees x 20 embeddings = 100k ve
- **P2.5** [RELIABILITY] **Unbounded growth of cluster cooldown, training auto_last, and lifetime dicts** — `backend/app/services/unknown_capture_service.py` — Multiple in-process dicts grow with no eviction: UnknownCaptureService._last_capture_monotonic accumulates one entry per cluster_id (5000+ over years before purge), TrainingService._auto_last one per 
- **P2.6** [PERFORMANCE] **session_scope commits even on no-op reads — pool churn** — `backend/app/api/deps.py` — `get_db()` (used by every endpoint via `Depends(get_db)`) calls `db.commit()` after every successful request — including pure-read GET endpoints. Postgres turns that into a BEGIN/COMMIT around a singl
- **P2.7** [RELIABILITY] **Snapshot directory structure is flat one-level — inode pressure** — `backend/app/services/snapshot_service.py` — Snapshots are organized YYYY-MM-DD/employee_id/file.jpg. On a busy day, 300 employees × 20 events × 365 days = ~2.2M files/year. Each day's directory has 300 subdirectories with ~20 files each — fine.
- **P2.8** [OBSERVABILITY] **Log rotation lacks ops-friendly diagnostic logs** — `backend/app/core/logger.py` — RotatingFileHandler with maxBytes=100MB and backupCount=5 = 500 MB ceiling, fine for retention. BUT: (a) only ONE file (app.log) for all subsystems — when RTSP errors flood the log, attendance events 
- **P2.9** [RELIABILITY] **Health loop iteration not bounded by global timeout — slow restarts pile up** — `backend/app/workers/camera_manager.py` — The health loop calls `self.restart(cam_id, skip_probe=True)` synchronously inside the for-loop. Each restart() acquires the per-camera lock (3 s timeout) and waits up to 5 s to join the old worker. W
- **P2.10** [FRONTEND_SECURITY] **No CSRF protection if cookie auth is adopted; current Bearer path is also vulnerable to mixed flows** — `backend/app/main.py` — CORS is configured with `allow_credentials=True` and `allow_methods=['*']`, `allow_headers=['*']`. While `allow_origins` is currently an allowlist, any future operator who pastes `*` (a common mistake
- **P2.11** [SECURITY] **Username enumeration via timing — bcrypt only runs when user exists** — `backend/app/services/auth_service.py` — When the username is unknown, `authenticate()` returns immediately (no bcrypt). When the username exists, `verify_password` adds ~100 ms. The 100 ms delta is measurable over the LAN and enumerates val
- **P2.12** [SECURITY] **python-jose 3.3.0 has unpatched algorithm-confusion CVEs** — `backend/requirements.txt` — python-jose 3.3.0 (last release 2022) has known issues including CVE-2024-33663 (algorithm confusion with OpenSSH ECDSA keys) and CVE-2024-33664 (JWE decompression DoS). The project is largely abandon
- **P2.13** [SECURITY] **Password policy is min-length 8 only — no complexity, history, or rotation** — `backend/app/schemas/auth.py` — `ChangePasswordRequest.new_password` enforces only `min_length=8`. There is no complexity check (uppercase/digit/symbol), no breach-list comparison, no reuse prevention (compares only against the imme
- **P2.14** [DEPLOYMENT_OPS] **No CLI/maintenance command to rotate JWT secret without orphaning all sessions silently** — `DEPLOYMENT` — There is no documented procedure for rotating `JWT_SECRET_KEY` (a basic compliance requirement and the natural response to a suspected compromise). Because the secret is read once via `@lru_cache` in 
- **P2.15** [DATA_INTEGRITY] **Endianness assumption — embedding bytes break across CPU architectures** — `backend/app/services/embedding_cache.py` — All four storage paths (EmployeeFaceEmbedding.vector, UnknownFaceCluster.centroid, UnknownFaceCapture.embedding, and the pack/unpack pair) use `np.ascontiguousarray(v.astype(np.float32)).tobytes()` an
- **P2.16** [DATA_INTEGRITY] **snapshot_path / file_path on disk are not reconciled with DB** — `backend/app/services/snapshot_service.py` — Three places write JPGs and store the path in the DB: SnapshotService (attendance_events.snapshot_path), TrainingService._persist_face (employee_face_images.file_path), and UnknownCaptureService (unkn
- **P2.17** [DATA_INTEGRITY] **Camera fps_override CHECK is the only sanity bound in DB** — `backend/app/models/attendance_settings.py` — 0006 added `ck_cameras_fps_override_range` for the new column. Every other numeric column in attendance_settings (face_match_threshold, face_min_quality, cooldown_seconds, camera_fps, train_min_images
- **P2.18** [EDGE_CASES] **close_day is non-idempotent across timezone or DST changes** — `backend/app/services/daily_attendance_service.py` — close_day uses local_day_bounds(work_date) to pick events to reclassify, then mutates them in-place (event_type IN→OUT, is_manual=True). If the operator reruns close_day after a timezone setting chang
- **P2.19** [FRONTEND_RESILIENCE] **Many icon-only buttons lack aria-labels — keyboard/SR users blocked** — `frontend/components/cameras/camera-table.tsx` — Multiple icon-only buttons render a Lucide icon child with no `aria-label`, no visually-hidden label, and no `<span class="sr-only">`. ShadCN `<Button size="icon">` does not auto-label. Some buttons u
- **P2.20** [FRONTEND_RESILIENCE] **Forms lose unsaved input on dialog close — no draft preservation** — `frontend/components/cameras/camera-wizard-dialog.tsx` — The Camera Wizard's effect `if (open) { setStep(1); setState(DEFAULT_STATE); ... }` runs every time the dialog opens, blowing away any in-progress entry. If the admin accidentally clicks outside the d
- **P2.21** [PERFORMANCE] **Snapshot grid creates one blob URL per card — memory grows with page size** — `frontend/components/shared/auth-image.tsx` — `AuthImage` calls `useSnapshotUrl(eventId)` which fetches and creates one `URL.createObjectURL(blob)` per mounted card. The Snapshots page can render 100+ cards. Each fetch is also un-cached (the hook
- **P2.22** [FRONTEND_RESILIENCE] **SnapshotViewer download relies on the same blob URL it displays — race on close** — `frontend/components/snapshots/snapshot-viewer.tsx` — `download()` sets `a.href = url` (the blob URL from `useSnapshotUrl`), appends/clicks/removes the anchor. If the user clicks Download and immediately navigates with arrow keys (which the same componen
- **P2.23** [FRONTEND_RESILIENCE] **Mobile users see no navigation — sidebar is hidden < lg breakpoint** — `frontend/components/layout/sidebar.tsx` — Sidebar uses Tailwind `hidden lg:flex` — invisible below 1024 px. Topbar (`components/layout/topbar.tsx`) contains no mobile menu trigger, no Sheet/Drawer, no hamburger button. Below `lg`, the navigat
- **P2.24** [OBSERVABILITY] **No log rotation safety: 100 MB × 5 backups exposes disk-fill risk** — `backend/app/core/logger.py` — RotatingFileHandler maxBytes=104857600 × 5 = 500 MB of logs at most. That's fine for size, but Python's RotatingFileHandler is NOT multi-process safe — if a future deployment runs multiple uvicorn wor
- **P2.25** [PERFORMANCE] **Health loop spins on zero cameras, no graceful idle** — `backend/app/workers/camera_manager.py` — When ALL cameras are inactive or zero cameras exist at startup, `_health_loop` still wakes every `CAMERA_HEALTH_INTERVAL_SECONDS` (default 10s), iterates an empty `_workers` dict, and goes back to sle
- **P2.26** [DATA_INTEGRITY] **delete_image leaves orphan FK if rmtree happens to fail after DB delete** — `backend/app/services/training_service.py` — Order is: DB delete → `db.flush()` → file unlink (in try/except). If the DB delete succeeds but unlink fails (file in use, permission denied), the DB row is gone but the file remains. The reverse case
- **P2.27** [PERFORMANCE] **FaceService._lock serializes ALL camera detection — single point of contention** — `backend/app/services/face_service.py` — `detect()` acquires `self._lock` for the entire `app.get(frame_bgr)` call. With 4-8 cameras all running 1 FPS detection, they serialize through this lock. If InsightFace ever hangs (CUDA driver crash,
- **P2.28** [EDGE_CASES] **No model-file checksum / integrity check at startup** — `backend/app/services/face_service.py` — InsightFace `buffalo_l` models live under `FACE_MODEL_ROOT` (default `./storage/models`). If a model file gets truncated (mid-download, disk error during years of use, ransomware partial encryption), 
- **P2.29** [FRONTEND_SECURITY] **Token may end up in URL via `?next=` on auth-required deep links** — `frontend/middleware.ts` — Middleware stores the requested path in `?next=pathname`. If an admin shares a Sentry/error report, a screenshot, or a Slack link of an auth-redirected URL, it leaks the internal path (e.g. `/login?ne
- **P2.30** [FRONTEND_RESILIENCE] **No multi-tab logout sync — sibling tabs stay 'logged in'** — `frontend/lib/auth/context.tsx` — Logging out in tab A does `clearToken()` (deletes the cookie) and `router.replace('/login')` in that tab only. Tab B still holds `admin` in React state, still renders the dashboard, and only discovers
- **P2.31** [SECURITY] **No idle timeout — admin session lives the full 24h even unattended** — `frontend/lib/auth/context.tsx` — Token TTL is 1440 minutes (24h). There is no client-side idle timer that signs the user out after N minutes of inactivity, and no sliding-window refresh either. An admin who logs in at 9am and walks a
- **P2.32** [PRIVACY_COMPLIANCE] **Snapshot blob URLs leak biometric data via revoke timing race** — `frontend/lib/hooks/use-attendance.ts` — `useSnapshotUrl` does `URL.createObjectURL(blob)` and revokes it on effect cleanup — good. BUT the blob URL is set on `<img src>` and the cleanup runs as soon as `eventId` changes; if the user scrolls
- **P2.33** [FRONTEND_SECURITY] **Sequential employee IDs in URLs allow enumeration via authed user** — `frontend/app/(dashboard)/training/page.tsx` — URLs throughout the dashboard use sequential integer IDs (`?employee=47`, `/employees/47`, `/cameras/3`, etc.). A VIEWER role user (per the RBAC model SUPER_ADMIN/ADMIN/VIEWER) can change the URL `?em
- **P2.34** [FRONTEND_RESILIENCE] **AuthProvider 401-clear races with in-flight requests** — `frontend/lib/api/client.ts` — On any 401, the axios interceptor calls `clearToken()` immediately. If the dashboard has 5 parallel `useQuery` requests in flight and ONE returns 401 (e.g. token expired mid-load), `clearToken()` runs
- **P2.35** [SECURITY] **No password complexity policy enforced on change-password** — `backend/app/services/auth_service.py` — `change_password` only checks current password matches and new != current. There's no minimum length, no complexity rule, no "must not equal username", no "must not equal `ChangeMe@123`", no breach-li
- **P2.36** [FRONTEND_SECURITY] **No security headers (HSTS, X-Frame, X-Content-Type, CSP)** — `frontend/next.config.mjs` — Neither the Next.js config nor the FastAPI app sets standard security headers. No CSP (XSS amplification), no X-Frame-Options (click-jacking), no X-Content-Type-Options (MIME sniffing), no Referrer-Po
- **P2.37** [PRIVACY_COMPLIANCE] **Cooldown bookkeeping is in-process and resets on every restart — same person re-captured** — `backend/app/services/unknown_capture_service.py` — The per-cluster cooldown that suppresses duplicate unknown captures uses an in-process dict keyed by cluster_id and time.monotonic(). On every uvicorn restart (config change, crash, OS reboot, log rot
- **P2.38** [PRIVACY_COMPLIANCE] **Default-off unknown_capture has no review or auto-disable safeguard** — `backend/app/models/attendance_settings.py` — Good news: unknown_capture_enabled defaults to False. Bad news: once an ADMIN flips it on via PATCH /api/v1/settings, the system captures every visitor's face indefinitely with no scheduled review, no
- **P2.39** [PRIVACY_COMPLIANCE] **No anonymous/embedding-only mode — face JPGs are always retained** — `backend/app/services/snapshot_service.py` — Every attendance event writes a face crop JPG to disk and every unknown capture stores the face image. There is no operator-mode for 'embeddings-only' — i.e., store the 512-d vector for recognition bu
- **P2.40** [PRIVACY_COMPLIANCE] **Children's data path: no flag/handling for visitors-with-minors** — `backend/app/services/unknown_capture_service.py` — DPDP S.9 explicitly requires verifiable parental consent for processing personal data of children (<18). If a visitor brings a child past the camera, the unknown-capture pipeline silently treats them 
- **P2.41** [PRIVACY_COMPLIANCE] **Email + phone of employees stored without justified business need** — `backend/app/models/employee.py` — Employee table stores `email` and `phone` but the system never actually sends them anything — there is no notification service, no password-reset-via-email, no SMS alert. These are pure HR-style metad
- **P2.42** [OBSERVABILITY] **Logs only on disk — no operator alerting on critical failures** — `backend/app/core/logger.py` — Logs go to stdout and `logs/app.log` (RotatingFileHandler 100MB x 5 = 500MB cap — fine for retention but useless for alerting). When a camera goes DEGRADED, when the InsightFace model fails to load, w
- **P2.43** [DEPLOYMENT_OPS] **Frontend production process unstarted/unsupervised — `npm run dev` documented** — `README.md` — The top-level README documents `npm run dev` for the frontend — that is Next.js's dev server, full of debug overhead, hot-reload, source maps, and unsafe-eval CSP. There is no documented `npm run buil
- **P2.44** [DEPLOYMENT_OPS] **No `.env` backup or secret-management procedure documented** — `DEPLOYMENT` — `backend/.env` holds the only copy of `JWT_SECRET_KEY` (which, when changed, invalidates every active session — acceptable) and `BOOTSTRAP_ADMIN_PASSWORD` (which, after first boot, is effectively dead