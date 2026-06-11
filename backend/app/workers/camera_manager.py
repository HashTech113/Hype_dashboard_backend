"""Orchestrates RTSP camera workers — the lifecycle layer above CameraWorker.

Responsibilities (audit-driven hardening):
  - Spawn 1 worker per active camera at startup
  - Restart workers when their URL/FPS changes (config push)
  - Run a health loop that detects stuck/dead workers and rebuilds them
  - Pre-probe new URLs before tearing down a working stream (audit E3)
  - Per-camera restart lock to prevent concurrent restart from leaking
    zombie threads (audit E5)
  - Use last_frame_age_seconds for health, not heartbeat (audit E1)
  - Surface inactive-camera restart as 409 to the API (audit E6)
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.core.exceptions import InvalidStateError, NotFoundError
from app.core.logger import get_logger
from app.db.session import session_scope
from app.repositories.camera_repo import CameraRepository
from app.services.cooldown_service import get_cooldown_service
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.workers.camera_worker import CameraWorker
from app.workers.rtsp_probe import probe_rtsp

log = get_logger(__name__)

# When a worker has been running this long without ever delivering a frame,
# treat it as "never connected" and restart (which re-reads the URL from DB,
# so a URL update gets picked up). 30s gives FFmpeg plenty of time to
# negotiate codec/auth on slow cameras.
_STARTUP_GRACE_SECONDS: float = 30.0

# Health-loop restart cooldown — if a worker has been auto-restarted by the
# health loop within the last N seconds, skip restarting it again. Prevents
# a permanently broken camera from churning forever (open → fail → restart
# → open → fail → restart). The operator's manual restart bypasses this.
_HEALTH_RESTART_COOLDOWN_SECONDS: float = 90.0


class CameraManager:
    def __init__(
        self,
        *,
        face_service: FaceService,
        embedding_cache: EmbeddingCache,
    ) -> None:
        self._lock = threading.Lock()
        self._workers: dict[int, CameraWorker] = {}
        self._face_service = face_service
        self._embedding_cache = embedding_cache
        self._cooldown = get_cooldown_service()
        self._health_thread: threading.Thread | None = None
        self._stop_health = threading.Event()
        # Per-camera restart locks — prevent two restart() calls (admin click
        # + health-loop trigger) from racing and leaking zombie threads.
        self._restart_locks: dict[int, threading.Lock] = {}
        self._restart_locks_lock = threading.Lock()
        # Lifetime stats per camera_id — survive restarts so the operator
        # doesn't see "0 events" after a transient hiccup auto-restarted.
        self._lifetime: dict[int, dict] = {}
        # Last time the health loop auto-restarted each camera. Used to throttle
        # the loop so a permanently broken camera doesn't restart-churn.
        self._last_health_restart: dict[int, float] = {}

    def _restart_lock_for(self, camera_id: int) -> threading.Lock:
        with self._restart_locks_lock:
            lock = self._restart_locks.get(camera_id)
            if lock is None:
                lock = threading.Lock()
                self._restart_locks[camera_id] = lock
            return lock

    def _build_worker(self, camera) -> CameraWorker:  # type: ignore[no-untyped-def]
        # Safe attribute fetch because some tests / code paths build a
        # Camera-shim object without the new fps_override column.
        fps_override = getattr(camera, "fps_override", None)
        return CameraWorker(
            camera_id=camera.id,
            camera_name=camera.name,
            rtsp_url=camera.rtsp_url,
            camera_type=camera.camera_type,
            face_service=self._face_service,
            embedding_cache=self._embedding_cache,
            cooldown_service=self._cooldown,
            fps_override=fps_override,
        )

    def start_all(self) -> None:
        with session_scope() as db:
            cameras = CameraRepository(db).list_active()

        with self._lock:
            for cam in cameras:
                if cam.id in self._workers and self._workers[cam.id].is_alive():
                    continue
                worker = self._build_worker(cam)
                worker.start()
                self._workers[cam.id] = worker
                log.info("Started worker for camera id=%s name=%s", cam.id, cam.name)

        if self._health_thread is None or not self._health_thread.is_alive():
            self._stop_health.clear()
            self._health_thread = threading.Thread(
                target=self._health_loop, name="camera-health", daemon=True
            )
            self._health_thread.start()

    def stop_all(self) -> None:
        self._stop_health.set()
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()
        for w in workers:
            w.join(timeout=5.0)
        if self._health_thread is not None:
            self._health_thread.join(timeout=2.0)
            self._health_thread = None
        log.info("All camera workers stopped")

    def stop(self, camera_id: int) -> None:
        """Stop and remove a single camera worker.

        Used by the DELETE endpoint before tearing down the camera row so
        no stale RTSP socket / drain thread / detection loop is left
        running referencing a deleted DB row. Idempotent — a no-op if the
        worker is already gone.
        """
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker is None:
            return
        worker.stop()
        worker.join(timeout=5.0)
        log.info("Camera worker id=%s stopped + removed from manager", camera_id)

    def restart(self, camera_id: int, *, skip_probe: bool = False) -> None:
        """Restart the worker for a camera.

        Workflow (audit-hardened):
          1. Acquire per-camera lock — only one restart at a time.
          2. Bail if we're shutting down (so health-loop can't spawn zombies).
          3. Read the camera row.
          4. If inactive: stop any running worker, return.
          5. (Optional) Probe the NEW URL first — if it's broken, REFUSE to
             tear down the working old worker. The operator gets a clear
             error and the camera stays up.
          6. Stop old worker, join with timeout, verify it died.
          7. Build new worker, start, register.

        skip_probe=True is for internal callers (startup, health recovery)
        that already know they need to rebuild.
        """
        lock = self._restart_lock_for(camera_id)
        if not lock.acquire(timeout=3.0):
            log.warning(
                "Restart for camera id=%s blocked by concurrent restart — abandoning",
                camera_id,
            )
            return
        try:
            # Race with stop_all: if we're shutting down, refuse — otherwise
            # the new worker becomes a leaked zombie since _workers gets
            # cleared after stop_all is called.
            if self._stop_health.is_set():
                log.info("Restart for camera id=%s skipped — manager is shutting down", camera_id)
                return
            with session_scope() as db:
                cam = CameraRepository(db).get(camera_id)
                if cam is None:
                    raise NotFoundError(f"Camera {camera_id} not found")
                cam_snapshot = (
                    cam.id,
                    cam.name,
                    cam.rtsp_url,
                    cam.camera_type,
                    cam.is_active,
                    getattr(cam, "fps_override", None),
                )

            # 3. Inactive — drop the running worker (if any) and return.
            if not cam_snapshot[4]:
                with self._lock:
                    existing = self._workers.pop(camera_id, None)
                if existing is not None:
                    existing.stop()
                    existing.join(timeout=5.0)
                log.info("Camera id=%s is inactive — worker stopped, not restarting", camera_id)
                return

            # 4. Pre-probe — refuse to break a working old worker for a bad new URL.
            if not skip_probe:
                outcome = probe_rtsp(cam_snapshot[2], timeout_ms=4000)
                if not outcome.ok:
                    with self._lock:
                        had_old = camera_id in self._workers and self._workers[camera_id].is_alive()
                    if had_old:
                        # Keep the old (working) worker running — refuse the restart.
                        raise InvalidStateError(
                            f"Refusing restart: the new URL did not open "
                            f"({outcome.error or 'unknown'}). The current worker "
                            f"is left running. Fix the URL or restart with "
                            f"force=true to drop the working stream anyway."
                        )
                    # No existing worker — start anyway; better some attempt than none.

            # 5. Stop & join old worker
            with self._lock:
                existing = self._workers.pop(camera_id, None)
            if existing is not None:
                existing.stop()
                existing.join(timeout=5.0)
                if existing.is_alive():
                    # Old worker is wedged. Log it loudly but proceed — we have
                    # a per-camera lock so we won't start a second worker for it.
                    log.error(
                        "Worker for camera id=%s did not stop within 5s — "
                        "likely wedged in cv2.read. Starting new worker; "
                        "old thread leaks until process restart.",
                        camera_id,
                    )

            # 6. Build & start the new worker
            class _Shim:
                def __init__(self, data):
                    (
                        self.id,
                        self.name,
                        self.rtsp_url,
                        self.camera_type,
                        self.is_active,
                        self.fps_override,
                    ) = data

            worker = self._build_worker(_Shim(cam_snapshot))
            worker.start()
            # H2 fix: re-check the shutdown flag UNDER the lock right before
            # registering. Without this, stop_all() can complete between the
            # early check (above) and this insert — leaving the new worker
            # as a zombie holding an RTSP connection + emitting duplicate
            # attendance events for the same camera_id.
            abandon = False
            with self._lock:
                if self._stop_health.is_set():
                    abandon = True
                else:
                    self._workers[camera_id] = worker
                    self._lifetime.setdefault(
                        camera_id,
                        {"restarts": 0, "frames": 0, "events": 0},
                    )["restarts"] += 1
                    restart_count = self._lifetime[camera_id]["restarts"]

            if abandon:
                log.info(
                    "Restart for camera id=%s abandoned — manager shut down mid-flight; "
                    "stopping the new worker that was already starting.",
                    camera_id,
                )
                worker.stop()
                # Join OUTSIDE the lock so we don't pin _lock while waiting
                # on the worker thread's RTSP read to time out.
                worker.join(timeout=5.0)
                return
            log.info("Restarted worker for camera id=%s (restart #%d)",
                     camera_id, restart_count)
        finally:
            lock.release()

    def get_latest_frame(self, camera_id: int, *, max_age_seconds: float = 5.0):
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None or not worker.is_running:
            return None
        return worker.get_latest_frame(max_age_seconds=max_age_seconds)

    def get_preview_jpeg(
        self,
        camera_id: int,
        *,
        annotated: bool,
        max_age_seconds: float,
        quality: int = 80,
    ) -> bytes | None:
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None or not worker.is_running:
            return None
        snapshot = worker.get_latest_preview(max_age_seconds=max_age_seconds)
        if snapshot is None:
            return None
        from app.services.preview_service import annotate_frame, encode_jpeg

        frame, detections = snapshot
        if annotated and detections:
            frame = annotate_frame(frame, detections, in_place=True)
        return encode_jpeg(frame, quality=quality)

    def stream_mjpeg(
        self,
        camera_id: int,
        *,
        annotated: bool = True,
        quality: int = 70,
        max_fps: int = 30,
        max_width: int = 1280,
    ):
        """Yield a multipart/x-mixed-replace MJPEG stream for a camera.

        Used by GET /cameras/{id}/preview.mjpeg to deliver near-realtime
        video to the browser without the per-frame round trip cost of
        JPEG polling. One persistent connection, JPEG frames pushed as
        soon as the worker captures a new frame.

        Yields raw bytes — boundaries + headers + image body — suitable
        for direct streaming via FastAPI's StreamingResponse.

        Latency floor is the camera's native frame interval plus ~10-20ms
        for JPEG encode + TCP send. On a 15 fps Hikvision sub-stream that's
        ~80ms total — about 10× lower than HTTP polling at 200ms intervals.

        Generator stops cleanly when:
          - The worker is removed from the manager (camera disabled/deleted)
          - The client disconnects (StreamingResponse handles the cleanup)
          - Manager shutdown is signalled
        """
        import time as _time
        from app.services.preview_service import annotate_frame, encode_jpeg

        boundary = "frame"
        last_frame_at: float = 0.0
        # Sleep BETWEEN sends only as much as needed to enforce max_fps —
        # but never block longer than 10ms when a fresh frame is ready,
        # because that's how a slow generator caps the achievable rate
        # below the camera's native FPS. Most cameras run at 15-30 fps so
        # max_fps=30 means min_interval=33ms — fine when the camera is the
        # bottleneck, harmful when the camera is faster.
        min_send_interval = 1.0 / max(1, max_fps)
        # Polling for "is there a new frame yet" — sleep this long when
        # the answer is no. Must be short enough to NOT throttle below
        # the camera's frame interval (~33-67 ms for 15-30 fps cameras).
        IDLE_POLL_S = 0.005  # 5ms = 200 polls/sec when idle
        last_send_at: float = 0.0

        # First — verify the camera even exists / is running
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None or not worker.is_running:
            # Yield one informational frame so the browser doesn't show a
            # blank <img>, then close.
            yield self._error_mjpeg_frame(boundary, "Camera not running")
            return

        try:
            while not self._stop_health.is_set():
                # Look up worker each loop in case it was restarted.
                with self._lock:
                    worker = self._workers.get(camera_id)
                if worker is None or not worker.is_running:
                    yield self._error_mjpeg_frame(boundary, "Camera stopped")
                    return

                # Fast path: peek at the frame timestamp first under lock,
                # only do the (expensive) frame copy if it's actually new.
                # This avoids a 2.7MB copy on every polling tick — the prior
                # version copied unconditionally then compared timestamps,
                # adding 5-10ms per idle poll and capping throughput.
                with worker._frame_lock:  # noqa: SLF001 — read-only field
                    frame_at = worker._latest_frame_at  # noqa: SLF001
                if frame_at <= last_frame_at:
                    _time.sleep(IDLE_POLL_S)
                    continue

                snapshot = worker.get_latest_preview(max_age_seconds=5.0)
                if snapshot is None:
                    # Frame disappeared between peek and snapshot (worker
                    # restart race). Loop and try again.
                    _time.sleep(IDLE_POLL_S)
                    continue
                last_frame_at = frame_at
                frame, detections = snapshot

                if annotated and detections:
                    # annotate_frame returns the same buffer when in_place=True,
                    # which is safe here because we have our own copy (the
                    # worker's _frame_lock copy semantics already gave us one).
                    frame = annotate_frame(frame, detections, in_place=True)

                # Downscale wide frames so the JPEG encode + transfer is fast
                # enough to keep up with the camera's native frame rate.
                # 4K (2560-3840 wide) takes 100+ms to encode at quality 70
                # which caps the stream at 5-8 fps. Resizing to 1280 wide
                # brings encode time under 25ms = 30+ fps achievable, while
                # the preview still looks HD.
                if max_width and frame.shape[1] > max_width:
                    import cv2 as _cv2  # local import keeps top-of-file clean
                    h_orig, w_orig = frame.shape[:2]
                    scale = max_width / w_orig
                    new_size = (max_width, int(round(h_orig * scale)))
                    # INTER_LINEAR is ~2× faster than INTER_AREA at similar
                    # quality for >0.5× downscales (which we always are when
                    # going 4K → 854/1280). The minor sharpness trade is
                    # invisible on a streaming preview.
                    frame = _cv2.resize(
                        frame, new_size, interpolation=_cv2.INTER_LINEAR
                    )

                jpeg = encode_jpeg(frame, quality=quality)

                # multipart/x-mixed-replace frame format:
                #   --boundary\r\n
                #   Content-Type: image/jpeg\r\n
                #   Content-Length: NNN\r\n\r\n
                #   <bytes>\r\n
                yield (
                    f"--{boundary}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(jpeg)}\r\n\r\n"
                ).encode("ascii") + jpeg + b"\r\n"

                # Enforce max_fps as a SOFT cap — only sleep enough to keep
                # the per-frame interval >= 1/max_fps. If encode+send already
                # took longer (which it will on a 1080p frame), don't add
                # gratuitous sleep on top.
                now = _time.monotonic()
                if last_send_at > 0:
                    elapsed = now - last_send_at
                    if elapsed < min_send_interval:
                        _time.sleep(min_send_interval - elapsed)
                last_send_at = _time.monotonic()
        except GeneratorExit:
            # Client disconnected — clean shutdown, no log spam.
            return
        except Exception:
            # Surfaces in the FastAPI error log via the streaming response.
            log.exception("MJPEG stream for camera_id=%s crashed", camera_id)
            return

    @staticmethod
    def _error_mjpeg_frame(boundary: str, message: str) -> bytes:
        """Encode a tiny 1x1 black JPEG with the error message in the
        Content-Type's name parameter. Browsers display NOTHING but the
        stream terminates cleanly so the <img> tag can fail-over."""
        # Minimal 1x1 black JPEG (130 bytes-ish)
        import io
        import numpy as np
        from app.services.preview_service import encode_jpeg
        try:
            jpeg = encode_jpeg(np.zeros((1, 1, 3), dtype=np.uint8), quality=10)
        except Exception:
            jpeg = b""
        return (
            f"--{boundary}\r\n"
            f"Content-Type: image/jpeg\r\n"
            f"X-Stream-Message: {message[:120]}\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n"
        ).encode("ascii") + jpeg + b"\r\n"

    def status(self) -> list[dict]:
        out: list[dict] = []
        with self._lock:
            workers = dict(self._workers)
            lifetime = dict(self._lifetime)
        for cam_id, w in workers.items():
            lt = lifetime.get(cam_id, {"restarts": 0, "frames": 0, "events": 0})
            out.append(
                {
                    "camera_id": cam_id,
                    "camera_name": w.camera_name,
                    "is_running": w.is_running,
                    "last_heartbeat_age_seconds": w.last_heartbeat_age_seconds,
                    "last_frame_age_seconds": w.last_frame_age_seconds,
                    "seconds_since_start": w.seconds_since_start,
                    "processed_frames": w.stats.processed_frames,
                    "events_generated": w.stats.events_generated,
                    "auto_enrollments": w.stats.auto_enrollments,
                    "unknown_captures": w.stats.unknown_captures,
                    "unknown_skipped": w.stats.unknown_skipped,
                    "consecutive_open_failures": w.stats.consecutive_open_failures,
                    "consecutive_read_failures": w.stats.consecutive_read_failures,
                    "total_reconnects": w.stats.total_reconnects,
                    "health_state": w.stats.health_state,
                    "fps_effective": w._effective_fps(),
                    "fps_override": w.fps_override,
                    "fps_detected": w.reader.detected_fps,
                    "lifetime_restarts": lt["restarts"],
                    "last_error": w.stats.last_error,
                    "last_heartbeat": datetime.now(tz=timezone.utc),
                }
            )
        return out

    def _health_loop(self) -> None:
        """Watch all workers, restart wedged or never-connected ones.

        Decision tree (per audit E1, C2):
          - Worker thread died: rebuild.
          - last_frame_age_seconds is None AND seconds_since_start >
            STARTUP_GRACE: never connected — rebuild (picks up new DB URL).
          - last_frame_age_seconds > FRAME_TIMEOUT: stream died — rebuild.
          - last_heartbeat_age_seconds > HEARTBEAT_TIMEOUT × 3: thread is
            wedged (heartbeat should always tick — if it doesn't the worker
            is deadlocked) — rebuild.
        """
        settings = get_settings()
        frame_timeout = float(getattr(settings, "CAMERA_HEARTBEAT_TIMEOUT_SECONDS", 30.0))
        # Wedged-thread threshold — heartbeat should be ticking sub-second.
        wedged_threshold = float(settings.CAMERA_HEARTBEAT_TIMEOUT_SECONDS) * 3

        while not self._stop_health.wait(settings.CAMERA_HEALTH_INTERVAL_SECONDS):
            try:
                with self._lock:
                    items = list(self._workers.items())
                for cam_id, worker in items:
                    reason: str | None = None

                    if not worker.is_alive():
                        reason = "thread died"
                    else:
                        frame_age = worker.last_frame_age_seconds
                        if (
                            frame_age is None
                            and worker.seconds_since_start > _STARTUP_GRACE_SECONDS
                        ):
                            reason = (
                                f"never delivered a frame in {worker.seconds_since_start:.0f}s — "
                                f"URL may be wrong"
                            )
                        elif frame_age is not None and frame_age > frame_timeout:
                            reason = f"no frames for {frame_age:.0f}s"
                        elif worker.last_heartbeat_age_seconds > wedged_threshold:
                            reason = (
                                f"worker thread wedged "
                                f"({worker.last_heartbeat_age_seconds:.0f}s since heartbeat)"
                            )

                    if reason is not None:
                        now_mono = time.monotonic()
                        last = self._last_health_restart.get(cam_id, 0.0)
                        if now_mono - last < _HEALTH_RESTART_COOLDOWN_SECONDS:
                            # Already restarted recently — let the reader's
                            # own DEGRADED backoff handle the bad URL. The
                            # operator can force restart from the UI any time.
                            continue
                        self._last_health_restart[cam_id] = now_mono
                        log.warning(
                            "Camera id=%s unhealthy (%s); auto-restarting (cooldown=%ds)",
                            cam_id,
                            reason,
                            int(_HEALTH_RESTART_COOLDOWN_SECONDS),
                        )
                        try:
                            self.restart(cam_id, skip_probe=True)
                        except Exception:
                            log.exception(
                                "Health-loop restart failed for camera id=%s", cam_id
                            )
            except Exception:
                log.exception("Camera health loop error")
