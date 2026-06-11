# Structural & Quality Audit — full punchlist
**Grade:** B  
**Total verified findings:** 106 of 106 raw  
**Counts:** HIGH=12, MEDIUM=25, LOW=22

## Overall verdict
This is a solid, thoughtfully-built B-grade codebase with clear architectural intent (FastAPI services + repositories, TanStack Query hooks + typed API layer) that has slowly accumulated structural drift and several real correctness/concurrency bugs as features piled on. The bones are good — recognition pipeline is sensible, the repository/service split exists, RTSP reader has been hardened, and the frontend follows modern Next.js conventions — but layering violations, a worrying RTSP read/release race, several "transaction-held-across-IO" patterns, and a handful of silent-failure error paths mean it is not yet "out of the world" stable. With a focused week of cleanup it can comfortably reach A-territory for the stated single-PC / 300-employee / multi-year deployment.

## Top three priorities
1. Concurrency safety in the camera stack: fix the RTSPReader.read()/release() race, the CameraManager.restart()/stop_all() race, and move TrainingService.cache.load_from_db() off the camera worker thread (via EmbeddingCache.append_employee). These three together eliminate the only realistic process-crash and ghost-worker scenarios — exactly the failures that wreck a 'runs for years' deployment.
2. Transaction discipline + silent-failure cleanup: reorder process_auto_event so the AttendanceEvent commits before the snapshot write (also pulls disk IO out of the open transaction), give UnknownPurgeService the two-phase delete-then-unlink treatment, fix lazy='selectin' on Employee.face_images/face_embeddings, and stop swallowing manager.restart() failures in the camera routes. This kills the 'silently lost attendance events / drained connection pool / orphan JPGs / dead cameras showing green' class of bugs in one sweep.
3. Observability + frontend error surface: register a catch-all exception handler with a request_id middleware, add isError handling to dashboard tiles (or a global QueryCache.onError toast), broaden the audit-log swallow with a failure counter exposed on /health/ready, and fix the 401-on-validation flow so users stop being mysteriously logged out. Cumulatively these turn 'something is wrong but I can't tell what' into actionable diagnostics — the single most important property of a long-lived single-PC deployment.

## Strengths
- Layering pattern is correct in the majority of the backend — BaseRepository + per-resource repositories + services + thin routes works as designed in employees, cameras, attendance, training, and unknowns. The places that violate it (compliance/admins/snapshots) are visible exceptions rather than the norm.
- Domain modeling is deliberate: clean enums in core/constants, cohesive schemas, well-thought-out unknown-face capture & clustering pipeline (HDBSCAN re-cluster, online matching, promotion to employee), and the daily_attendance materialization.
- Frontend conventions are modern and consistent across most features: TanStack Query hooks per resource, typed API layer, ShadCN component primitives, login/auth context. The trio pattern (api/hooks/types) is well established even where individual files have drift.
- Concurrency primitives exist where they should: per-camera restart locks, manager._lock, frame_lock, embedding cache RLock, cooldown service. The architecture acknowledged threading from day one rather than retrofitting it.
- Camera worker has real engineering thought: hysteresis on error state, startup grace, health restart cooldown, fast-path preview decoupled from detection cadence, dedicated RTSP reader thread, smart-connect wizard with vendor path tables.
- The compliance/audit table set (admin_audit_log, biometric_purge_log, consent_records) shows DPDP awareness was designed in, not bolted on.
- Migrations are present and incremental (0007+) rather than a single mega-revision — operational stability for the multi-year goal.
- The codebase is genuinely readable. Most modules are well-named, well-commented, and tell a coherent story — including comments that acknowledge known shortcuts (e.g. the explicit `_ = source_ip` and the unknown-capture pipeline trade-offs).

## HIGH (12) — ship-blockers for stability
### H1. [CONCURRENCY] RTSPReader.read() can race with concurrent release() — process crash risk
- **File:** `backend/app/workers/rtsp_reader.py`
- **Why it matters:** read() copies the VideoCapture handle under the lock then calls cap.read() OUTSIDE the lock, while _close()/stop() concurrently calls release() on the same underlying handle. OpenCV's FFmpeg backend is not safe under this — it can segfault the whole uvicorn process, taking down all cameras and the API. With no service supervisor yet, the box stays down until manual intervention. Triggered by routine admin restart actions.
- **Fix:** Hold self._lock for the duration of cap.read() so release() cannot overlap (RTSP_READ_TIMEOUT_MSEC bounds the wait). Alternatively add a 'read in progress' guard that release() waits on. Option A is simpler and matches OpenCV's actual thread-safety guarantees.
- **Effort:** SMALL

### H2. [CONCURRENCY] CameraManager.restart() races stop_all() — leaked zombie worker on shutdown/reload
- **File:** `backend/app/workers/camera_manager.py`
- **Why it matters:** restart() checks _stop_health.is_set() at L155 but does not register the new worker until L228. If stop_all() runs in between, the new worker is started after shutdown completes and runs forever in the background, holding an RTSP connection and emitting duplicate attendance events for the same camera_id. Prevents clean shutdown and can double-write events on reload.
- **Fix:** Re-check _stop_health.is_set() under self._lock right before registering the new worker; if set, stop() the freshly built worker without registering. Symmetrically, set _stop_health before stop_all begins and have it wait for in-flight restart locks to drain with a short timeout.
- **Effort:** SMALL

### H3. [ERROR_HANDLING] process_auto_event writes snapshot BEFORE event row — disk errors silently drop attendance events
- **File:** `backend/app/services/attendance_service.py`
- **Why it matters:** save_event_snapshot runs at L76 BEFORE event_repo.add at L93, all inside the camera worker's session_scope. A disk-full / AV-lock / NTFS quirk causes the whole function to raise, the worker's outer except sets last_error and continues — but the AttendanceEvent never lands in the DB. Real IN/OUT events are silently lost while the UI still shows 'STREAMING'. Also creates an orphan JPG on partial failure paths.
- **Fix:** Reorder: insert the AttendanceEvent (snapshot_path=None), commit, then write the snapshot in a follow-up update. On snapshot failure, log and leave snapshot_path null. This also pulls disk IO outside the DB transaction (related medium finding).
- **Effort:** SMALL

### H4. [CONCURRENCY] TrainingService.auto_enroll calls cache.load_from_db() on the camera worker thread
- **File:** `backend/app/services/training_service.py`
- **Why it matters:** Every auto-enrollment rebuilds the entire embedding cache (full SELECT of 6000+ LargeBinary vectors, decode, vstack) on the camera worker thread, blocking RTSP reads for hundreds of ms. With auto-enroll on a busy camera this happens repeatedly. Live preview stutters, detection cadence drops, and concurrent rebuilds contend on the cache lock with recognition.
- **Fix:** Add EmbeddingCache.append_employee(employee_id, vectors) that vstacks new rows under the lock — no DB round-trip. Use from auto_enroll and single-image add. Keep load_from_db() only for delete and bulk-import. Better still: route rebuilds to a dedicated debounced thread.
- **Effort:** MEDIUM

### H5. [PERFORMANCE] Employee model lazy='selectin' on face_images & face_embeddings — pulls 2KB LargeBinary vectors on every employee load
- **File:** `backend/app/models/employee.py`
- **Why it matters:** Any path loading an Employee (employees list, presence, dashboard, timeline joins, daily report, get_by_ids) silently issues two extra SELECTs that hydrate every face image and every embedding vector — 100-1000x data the API never returns. Dashboard and presence polls pay this on every refresh. ORM memory churn is significant.
- **Fix:** Change both relationships to lazy='select' (default lazy). The one site that needs them eagerly (EmbeddingRepository.list_active_with_employee) already uses an explicit join, so it is unaffected. Add selectinload(...) only where actually needed.
- **Effort:** SMALL

### H6. [DATABASE] DailyAttendanceService.recompute_range — N×M query storm in one open transaction
- **File:** `backend/app/services/daily_attendance_service.py`
- **Why it matters:** Nested employee × date loop fires 3-4 queries per (employee, date) inside a single open transaction. A quarter-range recompute over 100 employees = 30,000+ round-trips serialized. Postgres locks accumulate; the connection pool drains; camera attendance INSERTs stall — cameras stop logging events for the duration on the single-PC deployment.
- **Fix:** One range query grouped by (employee_id, work_date) plus a bulk INSERT ... ON CONFLICT DO UPDATE per chunk, committing between chunks so the transaction does not span the whole job.
- **Effort:** MEDIUM

### H7. [CONCURRENCY] UnknownPurgeService deletes rows and does file IO inside one transaction
- **File:** `backend/app/services/unknown_purge_service.py`
- **Why it matters:** The purge loop interleaves db.delete(), Path.unlink(), and shutil.rmtree() inside one open transaction. Row locks block any concurrent camera worker insert of new captures for the full duration of file IO — which on Windows over thousands of small JPGs is tens of seconds. The unknown-capture pipeline freezes whenever an admin clicks Purge.
- **Fix:** Phase 1: short transaction that DELETEs rows with RETURNING file_path, commit. Phase 2: outside any transaction, unlink files and rmtree the directory tree.
- **Effort:** MEDIUM

### H8. [ERROR_HANDLING] No catch-all exception handler — non-AppError errors leak unhandled, no request_id to correlate logs
- **File:** `backend/app/main.py`
- **Why it matters:** Only AppError has a handler. sqlalchemy OperationalError, OSError on snapshot write, ValueError, etc. fall through to FastAPI's default with no request-id middleware. Operators cannot correlate a user-reported failure with backend logs. Transient DB outages return 500 instead of 503, defeating frontend retry policy and leaking stack traces in debug mode.
- **Fix:** Register @app.exception_handler(Exception) returning a sanitized 500 with a generated request_id (also added by middleware to every log line). Map sqlalchemy.exc.OperationalError / DBAPIError to 503 explicitly.
- **Effort:** SMALL

### H9. [ERROR_HANDLING] Camera-create/update/delete endpoints silently swallow worker-start failures
- **File:** `backend/app/api/v1/cameras.py`
- **Why it matters:** Four endpoints wrap manager.restart(...) in bare except Exception: log.exception(...). InvalidStateError (e.g. 'new URL did not open') and NotFoundError are swallowed; the API returns 200, the UI toast says 'Camera updated', but the worker is dead. The operator only discovers it via the next /cameras/health poll.
- **Fix:** Re-raise AppError subclasses so they propagate to the global handler. Or extend CameraRead with worker_started: bool / worker_error: str | None so the frontend can show a warning toast when the row saved but the worker failed.
- **Effort:** SMALL

### H10. [PERFORMANCE] Live preview frame deep-copied on EVERY worker tick (write-side defensive copy)
- **File:** `backend/app/workers/camera_worker.py`
- **Why it matters:** _set_latest_frame_only does self._latest_frame = frame.copy() on every camera tick even though the worker owns the frame and consumers always copy on the way out. At 1080p × 4 cameras × 5 FPS that's ~120 MB/s of redundant memcpy on the hot detection threads — competing with InsightFace for L2/L3 cache on a single-PC deployment.
- **Fix:** Drop the .copy() in _set_latest_frame_only and _set_latest_frame. Keep the get-side copy. Add a docstring noting the invariant: worker hands off ownership; never mutates after publish.
- **Effort:** SMALL

### H11. [ERROR_HANDLING] Dashboard components have no isError branch — failures silently render zeros / em-dashes
- **File:** `frontend/components/dashboard/stats-grid.tsx`
- **Why it matters:** Every dashboard tile destructures only { data, isLoading }. On query failure, data is undefined and components render placeholder values, 'No events recorded', etc. — indistinguishable from a healthy-but-empty system. For 'years of error-free operation', the failure mode where stats silently lie is the worst kind — operators chase the wrong root cause.
- **Fix:** Surface isError at the component level with an AlertCircle and Retry button, or add a global QueryCache.onError in createQueryClient that fires a 'Dashboard data could not load: <message>' toast. Distinguish 'fetch failed' from 'empty result'.
- **Effort:** MEDIUM

### H12. [PERFORMANCE] Unknowns grid issues 24+ independent authenticated blob fetches with no shared cache
- **File:** `frontend/components/unknowns/unknown-face-image.tsx`
- **Why it matters:** Every ClusterCard uses useUnknownCaptureUrl, a raw useState/useEffect that does its own axios fetch + URL.createObjectURL. PAGE_SIZE=24 produces 24 simultaneous auth fetches on first paint, queues at Chrome's 6-per-origin cap, and re-fetches everything on every list refetch and on the detail dialog open. Visible slowness on the /unknowns page as captures accumulate.
- **Fix:** Convert useUnknownCaptureUrl to useQuery with queryKey ['unknowns','capture-blob', captureId] and long staleTime/gcTime so the grid and detail dialog share blobs. Same shape for useSnapshotUrl. Optionally expose a thumbnail endpoint with a non-auth signed URL so the browser does the heavy lifting.
- **Effort:** MEDIUM

## MEDIUM (25)
### M1. [LAYERING] API routes bypass repositories with direct SQLAlchemy select/update calls
- **File:** `backend/app/api/v1/compliance.py`
- **Why:** compliance.py, admins.py, and snapshots.py inline select(), db.get(), and bulk update() against the API session, with sqlalchemy imports buried inside function bodies. The codebase otherwise consistently uses BaseRepository — newcomers copy whichever pattern they read first. Schema changes (indexes, soft delete, tenant filter) must be applied in N places.
- **Fix:** Add list/count helpers to AdminRepository, ConsentRepository (new), BiometricPurgeRepository (new), and EventRepository. Replace every select() / update() in api/v1/ with a repo call. Optionally add a lint guard forbidding sqlalchemy imports outside repositories/.
- **Effort:** MEDIUM

### M2. [LAYERING] admins.py imports private _record_audit from auth_service — layering + module-boundary violation
- **File:** `backend/app/api/v1/admins.py`
- **Why:** Routes reach across modules to import a leading-underscore private helper of a different service. Three call sites depend on it. Refactoring auth_service silently breaks admins. Audit-write — a compliance concern — is hidden inside auth_service.
- **Fix:** Promote to a public AuditService (or audit_service.py) with record_admin_action(...). Update auth_service.py and admins.py to call the public API. Plan compliance writes through the same helper so source_ip lands consistently.
- **Effort:** SMALL

### M3. [LAYERING] compliance.py erasure route owns transaction lifecycle + post-commit file IO
- **File:** `backend/app/api/v1/compliance.py`
- **Why:** Route function calls explicit db.commit() on a session already managed by get_db, then runs file deletion + embedding cache reload inline via request.app.state. If post-commit work raises, the response still succeeds but the system is in an inconsistent state (cache stale, files left). Other erasure callers would have to reimplement this dance.
- **Fix:** Move post-commit choreography into ComplianceService / BiometricPurgeService.purge_and_finalize(cache) using FastAPI BackgroundTasks. The route validates the phrase, calls the service, returns.
- **Effort:** MEDIUM

### M4. [LAYERING] Routes hand-build complex schemas from joined ORM rows instead of using service DTOs
- **File:** `backend/app/api/v1/attendance.py`
- **Why:** attendance.py, admin.py, and unknowns.py walk joined relationships in list comprehensions to construct AttendanceEventDetailRead / TimelineItem / PresenceStatus. Same translation gets duplicated whenever a new endpoint surfaces the same data. Service-layer tests can't assert the shape callers actually see.
- **Fix:** Move row-to-DTO translation into the corresponding service (mirror the DashboardService.timeline pattern). Routes become thin pass-through.
- **Effort:** MEDIUM

### M5. [ORGANIZATION] CameraWorker.run() mixes 7 responsibilities in one ~130-line method
- **File:** `backend/app/workers/camera_worker.py`
- **Why:** Frame pacing, RTSP read, error-state hysteresis, fast-path preview, detection rate-limiting, recognition, attendance, unknown-capture, and auto-enroll all interlock in one loop. Adding a new pipeline stage forces surgery on the single run() loop and risks regressing existing flows; unit testing requires booting the whole thread.
- **Fix:** Split run() into _read_tick, _detect_and_dispatch(frame), _handle_match(face, match, frame). Add employee_name/employee_code to MatchResult so _face_to_detection becomes a 4-line constructor. Consider extracting the attendance-and-enroll pipeline into RecognitionPipelineService.
- **Effort:** LARGE

### M6. [ERROR_HANDLING] BaseRepository.update silently drops None — clearing nullable fields is impossible via the API
- **File:** `backend/app/repositories/base_repo.py`
- **Why:** update() does `if value is not None: setattr(...)`. EmployeeUpdate and CameraUpdate allow nullable fields like email, phone, designation, location; the routes use exclude_unset=True. A user sending {email: null} to clear the address gets a 200 OK with the email unchanged. DPDP partial-erasure requests fail silently.
- **Fix:** Drop the None guard — exclude_unset=True already means every key in data was explicitly sent. Routes that need to preserve fields should not include them.
- **Effort:** SMALL

### M7. [ERROR_HANDLING] change_password returns 401 for input-validation failures — logs the user out
- **File:** `backend/app/services/auth_service.py`
- **Why:** 'New password equals current' and 'New password too short' raise AuthenticationError → 401. The frontend axios interceptor treats every 401 as session-expiry: clears the token, wipes React Query cache, hard-redirects to /login. Users with too-short new passwords get teleported to login with no error message.
- **Fix:** Raise ValidationError (422) for length/equality checks; keep AuthenticationError (401) only for verify_password failure. Pre-empt at the Pydantic schema level where possible.
- **Effort:** SMALL

### M8. [ERROR_HANDLING] 401 interceptor logs the user out on ANY 401, not just session-expiry
- **File:** `frontend/lib/api/client.ts`
- **Why:** Every 401 with __auth!==false clears the cookie, wipes the cache, and redirects to /login?next=. Unsaved form state is destroyed. There is no 'session expired' notice. Combined with the change_password issue, validation errors throw the user out.
- **Fix:** Only act when the response body's error code is actually session-related (e.g. token_expired). Show a 'Session expired' toast before redirecting. Never redirect from /auth/change-password.
- **Effort:** MEDIUM

### M9. [ERROR_HANDLING] audit_log writes silently swallow exceptions — privileged actions may not be auditable
- **File:** `backend/app/services/auth_service.py`
- **Why:** _record_audit catches Exception and only log.exception(). For PASSWORD_CHANGED, ADMIN_CREATE/UPDATE/DEACTIVATE, the action succeeds with no audit row if the audit table is degraded. Under DPDP Sec 8(5), regulator requests for 'who changed admin X' may hit holes. Application appears healthy.
- **Fix:** Keep the swallow but increment a process-level audit_write_failures_total counter, surface in /health/ready as non-fatal, and trigger a frontend banner if > 0. Also promote _record_audit to a public AuditService.record(...).
- **Effort:** SMALL

### M10. [ERROR_HANDLING] camera_worker overwrites real exception with literal 'unknown_capture_pipeline'
- **File:** `backend/app/workers/camera_worker.py`
- **Why:** When the unknown-capture branch raises, last_error is set to a constant string instead of f'unknown_capture: {exc}' (which the parallel attendance branch correctly uses). Operators see 'unknown_capture_pipeline' in the health UI with no diagnostic — must SSH and grep the log.
- **Fix:** Change to f'unknown_capture: {exc}' (clipped to ~200 chars) matching L316. Keep the log.exception call.
- **Effort:** SMALL

### M11. [ERROR_HANDLING] detect_single collapses three distinct failures into one generic FaceRecognitionError
- **File:** `backend/app/services/face_service.py`
- **Why:** Dedicated NoFaceDetectedError, MultipleFacesError, LowQualityFaceError exist but are never raised. Training and /recognition/identify can't tell admins whether to retry with a clearer photo, center the face, or upload a different image — the same generic code surfaces for very different conditions.
- **Fix:** Raise the specific subclasses. Update the frontend to show targeted help text per err.code.
- **Effort:** SMALL

### M12. [ERROR_HANDLING] Camera health loop swallows all exceptions — silent failure if a code-reload breaks it
- **File:** `backend/app/workers/camera_manager.py`
- **Why:** Outer try/except Exception logs and continues. A permanent failure (broken attribute, exhausted pool) causes every iteration to log the same error while the thread stays 'alive' but does nothing. Auto-restart of dead workers is silently disabled.
- **Fix:** Track last_successful_iteration_at; expose via /health/ready. If older than CAMERA_HEALTH_INTERVAL × 3, mark unhealthy. After N consecutive iteration exceptions, escalate to CRITICAL.
- **Effort:** SMALL

### M13. [NAMING] Misleading comment claims FaceService.detect filters by face_min_quality (it doesn't)
- **File:** `backend/app/workers/camera_worker.py`
- **Why:** Comment says faces are gated by face_min_quality but detect() applies no quality filter — only detect_single does. Worker runs full recognition + cooldown + DB lookup on low-quality faces, and noisy embeddings drive borderline false positives.
- **Fix:** Move the min_quality filter from detect_single into detect (matches the comment) and eliminates a real class of false positives.
- **Effort:** SMALL

### M14. [NAMING] Twin modules admin.py and admins.py with confusable names and unrelated concerns
- **File:** `backend/app/api/v1/admin.py`
- **Why:** admin.py serves dashboard/stats/presence/live-status; admins.py does admin-user CRUD. Filenames differ by one character. schemas/admin.py contains stats schemas (not admin schemas — those live in schemas/auth.py). Three-way naming drift is a continual source of import confusion.
- **Fix:** Rename api/v1/admin.py → api/v1/dashboard.py (and schemas/admin.py → schemas/dashboard.py). Keep /admin URL prefix for back-compat or migrate to /dashboard.
- **Effort:** MEDIUM

### M15. [NAMING] Frontend Settings type missing 8 unknown_* fields the backend exposes
- **File:** `frontend/lib/types/settings.ts`
- **Why:** Backend SettingsRead has 8 unknown-face-pipeline fields (capture_enabled, min_face_quality, cooldown_seconds, retention_days, etc.). The frontend type omits them entirely, so admins cannot tune the unknown-capture pipeline from the UI, and PATCH round-trips may strip those keys.
- **Fix:** Add the 8 fields to frontend/lib/types/settings.ts and surface them on the Settings page. Long-term, generate the type from the OpenAPI schema with openapi-typescript so drift cannot recur.
- **Effort:** SMALL

### M16. [DATABASE] Snapshot list filters in Python after a paginated SQL query — pagination is broken
- **File:** `backend/app/api/v1/snapshots.py`
- **Why:** Route calls EventRepository.list_filtered(...) then post-filters `if i.snapshot_path` in Python. Page sizes shrink unpredictably; the user-visible 'load more' hits phantom end-of-list. The total returned is wrong.
- **Fix:** Add has_snapshot filter to list_filtered (it already exists on list_filtered_with_joins). Return a real total.
- **Effort:** SMALL

### M17. [DATABASE] Unbounded presence and daily-attendance endpoints have no pagination or hard cap
- **File:** `backend/app/api/v1/admin.py`
- **Why:** /admin/presence (polled every 10s) and /attendance/daily return one row per employee with no limit/offset. At 300 employees × 3 admin tabs that's a meaningful payload on the LAN. No upper bound for future deployments. /daily/employee/{id} accepts arbitrary date ranges.
- **Fix:** Add limit (default 100, max 500) + offset to both endpoints; hard-cap server-side at 1000 rows with truncated:true. Add a _assert_range check (already in ReportService) to date-range endpoints.
- **Effort:** MEDIUM

### M18. [DATABASE] Dashboard snapshot fires 9 sequential queries per poll × every admin tab
- **File:** `backend/app/services/dashboard_service.py`
- **Why:** DashboardService.snapshot() issues 9 small round-trips per call. With 4-5 hooks polling and 3-4 admin tabs, the dashboard alone keeps Postgres busy continuously and burns connection-pool slots.
- **Fix:** Collapse the cheap counts into one CTE / scalar-subselect query. Cache the snapshot in-process for ~5s so multiple admins reuse one computation.
- **Effort:** MEDIUM

### M19. [DATABASE] event_repo paginated lists run a full COUNT(*) on every page over a multi-million-row table
- **File:** `backend/app/repositories/event_repo.py`
- **Why:** list_filtered / list_filtered_with_joins / timeline run a separate count_stmt. attendance_events grows to millions of rows over months; COUNT becomes the dominant cost on every page request. Used by the dashboard timeline poll every 10s.
- **Fix:** Use func.count().over() as a window column on the same query (one round-trip). Or skip the COUNT entirely for unbounded queries (UI uses 'load more').
- **Effort:** SMALL

### M20. [DATABASE] Table naming mixes plural and singular without a rule (attendance_events vs admin_audit_log)
- **File:** `backend/app/models`
- **Why:** 9 plural tables vs 4 singular ones, no consistent rationale. Anyone writing manual SQL (and the reports do) has to look up names. FK and index names inherit the inconsistency.
- **Fix:** Pick plural (dominant); add an Alembic rename for daily_attendance → daily_attendances, biometric_purge_log → biometric_purge_logs, admin_audit_log → admin_audit_logs. attendance_settings is a singleton — keep and document.
- **Effort:** MEDIUM

### M21. [NAMING] PresenceStatus is a row schema on the backend but a string enum on the frontend
- **File:** `backend/app/schemas/dashboard.py`
- **Why:** Same identifier means two different things across the boundary. The 'status' field is also free-form str on the backend when it should be the enum the frontend uses. OpenAPI consumers get confused.
- **Fix:** Rename backend PresenceStatus(BaseModel) → PresenceEntry; add PresenceState enum in core/constants.py; type the status field as that enum.
- **Effort:** SMALL

### M22. [NAMING] PurgeResponse defined twice with different shapes — name collision
- **File:** `backend/app/api/v1/snapshots.py`
- **Why:** api/v1/snapshots.py:33 (inline) and schemas/unknowns.py:131 both declare PurgeResponse with totally different fields. OpenAPI and any auto-importer collide. The inline schema also breaks the schemas-live-in-schemas convention.
- **Fix:** Move snapshot purge models to schemas/snapshot.py. Rename to SnapshotPurgeResponse and UnknownPurgeResponse so the resource disambiguates.
- **Effort:** SMALL

### M23. [CONCURRENCY] session_scope held across snapshot/JPEG disk write — DB connection pool can drain under AV/IO spikes
- **File:** `backend/app/services/attendance_service.py`
- **Why:** JPG encode + filesystem write happens INSIDE the camera worker's open transaction. Windows NTFS with antivirus regularly spikes write_bytes to 50-200ms; the DB connection is parked the whole time. With pool_size=10 and 8 cameras, the pool can drain and unrelated API requests fail with QueuePool.LimitOverflow.
- **Fix:** Reorder process_auto_event (also fixes the snapshot-failure-drops-event HIGH). Same fix in UnknownCaptureService._process. Optionally route encode+write to a small bounded ThreadPoolExecutor.
- **Effort:** MEDIUM

### M24. [CONCURRENCY] FaceService._lock serializes InsightFace inference across all cameras
- **File:** `backend/app/services/face_service.py`
- **Why:** detect() holds self._lock for the entire 30-80ms app.get(frame) inference. Every camera worker + /recognition/identify + training + unknown-promotion serialize through one lock. At 8 cameras that's 640ms of wall time per second just to serialize detection.
- **Fix:** Drop the lock from detect(); ONNXRuntime sessions are documented thread-safe for read-only inference. Keep the lock only in load() to prevent double-init.
- **Effort:** SMALL

### M25. [CONCURRENCY] Preview JPEG encoded on every poll with no per-camera cache — wastes a CPU core at 8 cams
- **File:** `backend/app/workers/camera_manager.py`
- **Why:** get_preview_jpeg runs annotate + cv2.imencode on every request with no cache. 3 admins × 4-8 cams at 600ms polls = ~30 encodes/sec, all contending for the GIL with worker detection. At 8 cams this consumes half a core continuously on a CPU-bound box.
- **Fix:** Cache (annotated, quality) → jpeg_bytes on CameraWorker with TTL of (1 / camera_fps); re-encode only when _latest_frame_at moves. Optionally stream MJPEG so one producer feeds N consumers.
- **Effort:** MEDIUM

## LOW (22)
- **L1** [ORGANIZATION] **Dead code: _assert_transition_legal, timeline_filtered, TertiaryStats, StatsGrid, unused imports** — `backend/app/services/attendance_service.py` — Delete the four unused symbols and the two unused imports (os in compliance_service.py, session_scope in compliance.py). Note timeline_filtered is also logically broken — deleting it removes a future 
- **L2** [ORGANIZATION] **Magic JPEG quality and crop-pad constants scattered with inconsistent names** — `backend/app/services/snapshot_service.py` — Introduce app/core/constants_runtime.py with TRAINING_JPEG_QUALITY=92, EVENT_SNAPSHOT_JPEG_QUALITY=85, UNKNOWN_CAPTURE_JPEG_QUALITY=88, PREVIEW_JPEG_QUALITY=65, FACE_CROP_PAD_RATIO=0.25, DETECTION_INT
- **L3** [ORGANIZATION] **_recompute_centroid duplicated between UnknownCaptureService and UnknownReclusterService** — `backend/app/services/unknown_capture_service.py` — Extract to app/utils/embeddings.py as compute_l2_centroid(...). Add unit tests for zero-vector and degenerate-dim edge cases.
- **L4** [ORGANIZATION] **Two identical _client_ip helpers across auth.py and admins.py; compliance.py doesn't extract IP at all** — `backend/app/api/v1/auth.py` — Move client_ip(request) to app/api/deps.py (or app/core/http.py). Import from all three routers so erasure audit rows include source_ip too.
- **L5** [ORGANIZATION] **smart_rtsp_service.py is 946 lines mixing 5 unrelated concerns** — `backend/app/services/smart_rtsp_service.py` — Split into smart_rtsp/ package: result_types.py, vendor_paths.py, probes.py, onvif.py, service.py. Re-export public names from __init__.py.
- **L6** [ORGANIZATION] **ConsentScope enum lives in models/compliance.py instead of core/constants.py** — `backend/app/models/compliance.py` — Move ConsentScope to core/constants.py next to the other domain enums; re-export from models/compliance.py if legacy imports exist.
- **L7** [ORGANIZATION] **compliance.py router has no prefix; only outlier among v1 routers** — `backend/app/api/v1/compliance.py` — Split into consent.py (prefix='/consent') and erasure.py (prefix='/erasure') under tag 'compliance', preserving URLs.
- **L8** [ORGANIZATION] **useDashboardSnapshot fetched independently by 4 components on /dashboard** — `frontend/app/(dashboard)/dashboard/page.tsx` — Lift the hook to DashboardPage and pass data via props to PrimaryStats/SecondaryStats/PresenceChart. Removes 4-subscriber re-render fanout and unifies loading skeletons.
- **L9** [ORGANIZATION] **Topbar accepts a title prop the layout never passes — always says 'Dashboard'** — `frontend/components/layout/topbar.tsx` — Either drop the dead prop or wire it from usePathname + NAV_ITEMS lookup. One source of truth.
- **L10** [ORGANIZATION] **Sidebar hardcodes 'AI Attendance' and 'v1.0.0' separately from package.json** — `frontend/components/layout/sidebar.tsx` — Expose process.env.NEXT_PUBLIC_APP_VERSION via next.config.mjs (read from package.json at build). Move the brand string to components/layout/brand.ts.
- **L11** [FRONTEND] **useSnapshotUrl and useUnknownCaptureUrl duplicate identical blob-loading logic** — `frontend/lib/hooks/use-attendance.ts` — Extract useAuthBlobUrl(fetchBlob, id) into lib/hooks/use-auth-blob-url.ts. Both hooks become one-liners. Pairs nicely with the HIGH 'wrap in useQuery for shared cache' fix.
- **L12** [FRONTEND] **change-password page imports authApi directly instead of using a mutation hook** — `frontend/app/(dashboard)/change-password/page.tsx` — Add useChangePassword() in lib/hooks/use-auth.ts that wraps mutate/isPending + invalidates ['auth','me']. Replace manual submitting boolean and try/catch.
- **L13** [FRONTEND] **Camera wizard dialog is 622 lines in one component file** — `frontend/components/cameras/camera-wizard-dialog.tsx` — Move each step into its own file under components/cameras/wizard/. Keep FormState/DEFAULT_STATE/ProgressDots in wizard/index.tsx.
- **L14** [FRONTEND] **CameraPreviewTile per-second forceTick re-renders every tile** — `frontend/components/cameras/camera-preview-tile.tsx` — Replace per-tile setInterval(1000) with a single shared useNow(1000) lifted to LiveViewPage and passed as 'now' prop. 8 tiles share one timer.
- **L15** [FRONTEND] **Recharts data + dashboard slice arrays rebuilt every render (referential instability)** — `frontend/components/dashboard/presence-chart.tsx` — useMemo on slices keyed on data?.inside_office etc. Wrap PresenceChart / PrimaryStats / SecondaryStats / CameraPreviewTile in React.memo. Use select() in useDashboardSnapshot to project only fields ea
- **L16** [FRONTEND] **useUnknownClusterList queryKey embeds the raw params object — fetches on every keystroke** — `frontend/lib/hooks/use-unknowns.ts` — Debounce labelQuery (200-300ms via useDeferredValue) before feeding into params; or normalize the queryKey to ['unknowns','list', status, labelQuery.trim(), limit, offset].
- **L17** [FRONTEND] **CameraWizardDialog forward-only navigation loses probe state on Back** — `frontend/components/cameras/camera-wizard-dialog.tsx` — Clear probeResult when navigating from Step 2 → Step 3 (or hash the credentials and auto-re-probe when changed). Prevents operator saving against a stale probe.
- **L18** [FRONTEND] **useEffect deps exclude probe/connect.reset() with eslint-disable comments** — `frontend/components/cameras/camera-wizard-dialog.tsx` — Replace the eslint-disable with explicit deps [open, probe, connect] or extract reset into a useCallback. Same in camera-form-dialog.tsx and cluster-detail-dialog.tsx.
- **L19** [FRONTEND] **Color-only legend swatches and icon-only ghost buttons missing aria-label** — `frontend/app/(dashboard)/live/page.tsx` — Add filled vs hollow square (or icon) to the green/red legend swatches. Add aria-label='Camera actions' / 'Restart worker' to MoreHorizontal and Refresh icon buttons in cameras/employees/attendance ta
- **L20** [ERROR_HANDLING] **Toast errors drop ApiError.code and structured 422 detail** — `frontend/lib/hooks/use-cameras.ts` — Extend toastError to include err.code as description (sonner supports `description`). Pretty-print 422 detail arrays. Surface code in support tickets.
- **L21** [ERROR_HANDLING] **decode_image_bytes returns None with no diagnostic for unsupported formats (e.g. HEIC)** — `backend/app/utils/image_utils.py` — Magic-byte sniff (JPEG / PNG / etc.) before imdecode; raise UnsupportedImageFormatError with the detected magic so admins uploading HEIC from iPhone get a useful error.
- **L22** [ERROR_HANDLING] **EmbeddingCache.load_from_db catches only ValueError — one bad row crashes boot** — `backend/app/services/embedding_cache.py` — Broaden per-row except to Exception with log.exception(embedding_id). Track last_rebuilt_at / vectors_loaded / vectors_skipped on the cache. Wrap the lifespan call in try/except so service starts degr