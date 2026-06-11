from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from app.core.constants import CameraType
from app.core.logger import get_logger
from app.db.session import session_scope
from app.services.attendance_service import AttendanceService
from app.services.cooldown_service import CooldownService
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import DetectedFace, FaceService
from app.services.recognition_service import MatchResult, RecognitionService
from app.services.settings_service import get_settings_service
from app.services.training_service import TrainingService
from app.services.unknown_capture_service import UnknownCaptureService
from app.utils.time_utils import now_utc
from app.workers.rtsp_reader import RTSPReader

log = get_logger(__name__)

# Face detection runs at most once per this interval per worker, regardless
# of how fast `camera_fps` is set. With 4 cameras × InsightFace serialized
# on a single CPU lock, running at every frame becomes the bottleneck and
# makes the live preview lag. Reading still happens at full `camera_fps` so
# the preview stays smooth; recognition + attendance + unknown-capture only
# fire at the slower detection cadence — plenty for real-time tracking.
# 1 FPS detection per camera × 4 cameras × ~30 ms (at FACE_DET_SIZE=320)
# ≈ 120 ms wall time / sec ≈ 12% of one CPU core.
_DETECTION_INTERVAL_SECONDS: float = 1.0  # 1 detection/sec per camera

# Shared bounded thread pool for InsightFace detection across all cameras.
# Capping at 2 workers prevents context-switch thrashing on typical 4-core
# CPU deployments while still letting one camera's recognition+attendance
# post-processing overlap with another camera's inference.
# The model lock inside FaceService.detect still serializes the actual
# onnxruntime call (which is not guaranteed thread-safe for InsightFace's
# pre/post-processing pipeline), but submitting via the pool decouples
# camera worker scheduling from the call-site so cameras don't wait
# on each other's full detect+recognize+attend cycle — only on the
# pure inference window.
_DETECTION_POOL_MAX_WORKERS: int = 2
_detection_pool: ThreadPoolExecutor | None = None
_detection_pool_lock = threading.Lock()


def _get_detection_pool() -> ThreadPoolExecutor:
    """Lazy-initialize the shared detection executor on first use.

    Lazy so importing this module never spawns threads (matters for
    test isolation and for the FastAPI app factory which imports a lot
    at module load time before settings are even resolved).
    """
    global _detection_pool
    if _detection_pool is None:
        with _detection_pool_lock:
            if _detection_pool is None:
                _detection_pool = ThreadPoolExecutor(
                    max_workers=_DETECTION_POOL_MAX_WORKERS,
                    thread_name_prefix="face-detect",
                )
    return _detection_pool


@dataclass
class WorkerStats:
    processed_frames: int = 0
    events_generated: int = 0
    auto_enrollments: int = 0
    unknown_captures: int = 0
    unknown_skipped: int = 0
    # Failure counters — surfaced via /cameras/health for ops visibility.
    consecutive_open_failures: int = 0
    consecutive_read_failures: int = 0
    total_reconnects: int = 0
    last_heartbeat: float = field(default_factory=time.monotonic)
    last_error: str | None = None
    last_error_at: float | None = None
    health_state: str = "CONNECTING"


@dataclass(frozen=True)
class FrameDetection:
    """One face detected in the most recent frame, with its match result.

    Used by the live preview endpoint to render bounding boxes + labels on
    top of the frame. Populated each tick alongside `_latest_frame`.
    """

    bbox: tuple[int, int, int, int]
    label: str  # employee name when matched; "Unknown" otherwise
    score: float  # cosine similarity (0..1) — best score even when unmatched
    matched: bool  # True iff `score >= face_match_threshold`


class CameraWorker(threading.Thread):
    def __init__(
        self,
        *,
        camera_id: int,
        camera_name: str,
        rtsp_url: str,
        camera_type: CameraType,
        face_service: FaceService,
        embedding_cache: EmbeddingCache,
        cooldown_service: CooldownService,
        fps_override: int | None = None,
    ) -> None:
        super().__init__(name=f"cam-{camera_id}-{camera_name}", daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.camera_type = camera_type
        self.face_service = face_service
        self.embedding_cache = embedding_cache
        self.cooldown = cooldown_service
        self.fps_override = fps_override  # None = inherit from global settings
        self.recognition = RecognitionService(embedding_cache)
        self.reader = RTSPReader(rtsp_url, name=camera_name)
        self._stop_event = threading.Event()
        self.stats = WorkerStats()
        # Wall-clock time the worker thread started, used to distinguish
        # "fresh, give it 5s" from "never connected" in the health loop.
        self._started_at: float = time.monotonic()

        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._latest_frame_at: float = 0.0
        self._latest_detections: list[FrameDetection] = []
        # Pre-encoded JPEG bytes + the timestamp they were encoded from.
        # The worker's fast thread now ALSO produces a ready-to-send JPEG
        # at default-preview parameters (640px / quality 60). All WS
        # clients that accept the default params share these bytes —
        # encode happens ONCE per camera regardless of viewer count.
        # Per-client encode is still used when the client requests a
        # non-default max_width or quality (full-screen modal, etc).
        self._latest_jpeg: bytes | None = None
        self._latest_jpeg_at: float = 0.0
        # Condition that the live preview streamer (WebSocket / MJPEG)
        # waits on so it wakes up the INSTANT a new frame is published —
        # no polling overhead, no buffer build-up, no jitter from sleep
        # granularity. Worker calls notify_all() after every frame set.
        self._frame_event = threading.Condition(self._frame_lock)

    @property
    def seconds_since_start(self) -> float:
        return max(0.0, time.monotonic() - self._started_at)

    def _effective_fps(self) -> int:
        """Resolve the worker's read rate. Priority:

        1. Operator-set `fps_override` on the camera row (UI lets them cap
           to save CPU on a low-traffic door).
        2. The camera's NATIVE FPS auto-detected from the RTSP stream
           (cv2.CAP_PROP_FPS during _open). Using the real value gives the
           lowest possible end-to-end latency — we drain the camera at
           exactly the rate it produces.
        3. Global `camera_fps` from settings — last-resort when neither of
           the above is available (e.g. first ticks before stream opens).
        """
        if self.fps_override is not None and self.fps_override > 0:
            return self.fps_override
        detected = self.reader.detected_fps
        if detected is not None and detected > 0:
            return max(1, int(round(detected)))
        return max(1, get_settings_service().get().camera_fps)

    @property
    def is_running(self) -> bool:
        return self.is_alive() and not self._stop_event.is_set()

    @property
    def last_heartbeat_age_seconds(self) -> float:
        """Time since the worker's loop body last ran. Stays low whenever
        the worker isn't deadlocked — even if every RTSP read is silently
        failing. NOT a reliable 'camera is streaming' signal — use
        `last_frame_age_seconds` for that.
        """
        return max(0.0, time.monotonic() - self.stats.last_heartbeat)

    @property
    def last_frame_age_seconds(self) -> float | None:
        """Time since the most recent frame was successfully read from
        the RTSP stream. `None` until the very first frame arrives. When
        this grows past a few seconds, the camera is not actually
        streaming — show 'Reconnecting' / 'Stale', not 'Live'.
        """
        with self._frame_lock:
            if self._latest_frame is None or self._latest_frame_at <= 0.0:
                return None
            return max(0.0, time.monotonic() - self._latest_frame_at)

    def stop(self) -> None:
        self._stop_event.set()
        self.reader.stop()

    # Invariant: the worker hands off ownership of `frame` to these setters.
    # After publish, the worker MUST NOT mutate the array. Consumers (preview
    # endpoint, training capture) copy on the way out (see get_latest_*).
    # H10 fix: dropped the defensive .copy() on write — at 4 cams × 5 FPS ×
    # 1080p that was ~120 MB/s of redundant memcpy on the hot detection thread.

    def _set_latest_frame(
        self,
        frame: np.ndarray,
        detections: list[FrameDetection] | None = None,
    ) -> None:
        """Replace both frame and detections. Used when detection ran for this
        frame (so the boxes are exactly synced to it).
        """
        with self._frame_event:
            self._latest_frame = frame
            self._latest_frame_at = time.monotonic()
            self._latest_detections = list(detections or [])
            self._frame_event.notify_all()

    def _set_latest_frame_only(self, frame: np.ndarray) -> None:
        """Update just the frame (preserve last detections) — fast path
        used to keep the live preview at the camera's read rate even when
        face detection is rate-limited to a lower cadence.

        Detections from up to ~_DETECTION_INTERVAL_SECONDS ago are still
        drawn on the new frame. Box positions visibly lag the face by the
        detection interval; this is the standard trade-off real CCTV
        previews make and is much better than a stuttering feed.

        Also pre-encodes a default-preview JPEG so all WS clients sharing
        the default params get the encoded bytes for FREE — encode work
        happens once per camera regardless of viewer count.
        """
        # Encode OUTSIDE the lock so we don't block the worker's other
        # readers (manager.status, /health) while opencv runs.
        jpeg = self._encode_default_preview(frame)
        with self._frame_event:
            self._latest_frame = frame
            self._latest_frame_at = time.monotonic()
            if jpeg is not None:
                self._latest_jpeg = jpeg
                self._latest_jpeg_at = self._latest_frame_at
            self._frame_event.notify_all()

    # Default preview encode parameters — match the WS endpoint's
    # defaults so most clients get the shared bytes. Per-client encode
    # is still used for fullscreen modals etc that pass non-default
    # max_width / quality.
    _PREVIEW_MAX_WIDTH = 640
    _PREVIEW_QUALITY = 60

    def _encode_default_preview(self, frame: np.ndarray) -> bytes | None:
        """Annotate + resize + JPEG-encode for default WS preview params.
        Returns the encoded bytes. Called from the fast thread so encode
        cost is paid ONCE per camera frame, not once per WS client."""
        try:
            from app.services.preview_service import (
                annotate_frame,
                encode_jpeg,
            )
            import cv2 as _cv2
            # Snapshot detections under the lock so we don't race the
            # detection thread's _set_latest_detections.
            with self._frame_lock:
                dets = list(self._latest_detections)
            f = frame
            if dets:
                f = annotate_frame(f, dets, in_place=True)
            if f.shape[1] > self._PREVIEW_MAX_WIDTH:
                h_orig, w_orig = f.shape[:2]
                scale = self._PREVIEW_MAX_WIDTH / w_orig
                new_size = (
                    self._PREVIEW_MAX_WIDTH,
                    int(round(h_orig * scale)),
                )
                f = _cv2.resize(
                    f, new_size, interpolation=_cv2.INTER_NEAREST
                )
            return encode_jpeg(f, quality=self._PREVIEW_QUALITY)
        except Exception:
            log.exception("[%s] default preview encode failed", self.camera_name)
            return None

    def wait_next_jpeg(
        self, last_jpeg_at: float, *, timeout: float = 1.0
    ) -> tuple[bytes, float] | None:
        """Block until a JPEG newer than `last_jpeg_at` is available;
        return (jpeg_bytes, timestamp). Used by the WS endpoint as the
        fast-path frame source. The bytes are immutable so multiple WS
        clients hold the SAME reference — no per-client copy, no per-
        client encode."""
        with self._frame_event:
            ok = self._frame_event.wait_for(
                lambda: (
                    self._latest_jpeg is not None
                    and self._latest_jpeg_at > last_jpeg_at
                ),
                timeout=timeout,
            )
            if not ok or self._latest_jpeg is None:
                return None
            return self._latest_jpeg, self._latest_jpeg_at

    def _set_latest_detections(self, detections: list[FrameDetection]) -> None:
        """Update only the detections list — paired with `_set_latest_frame_only`
        when detection runs at a slower cadence than frame reads.
        """
        with self._frame_lock:
            self._latest_detections = list(detections)

    def get_latest_frame(self, *, max_age_seconds: float = 5.0) -> np.ndarray | None:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            if time.monotonic() - self._latest_frame_at > max_age_seconds:
                return None
            return self._latest_frame.copy()

    def get_latest_preview(
        self, *, max_age_seconds: float = 10.0
    ) -> tuple[np.ndarray, list[FrameDetection]] | None:
        """Latest frame + per-face detections for rendering an annotated
        preview. Returns None if there's no frame yet or it's too stale.
        """
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            if time.monotonic() - self._latest_frame_at > max_age_seconds:
                return None
            return self._latest_frame.copy(), list(self._latest_detections)

    def wait_next_preview(
        self,
        last_frame_at: float,
        *,
        timeout: float = 1.0,
    ) -> tuple[np.ndarray, list[FrameDetection], float] | None:
        """Block until a frame newer than `last_frame_at` is published,
        then return (copy, detections, timestamp). Returns None on timeout.

        Event-driven — no polling. Used by the WebSocket live-stream
        endpoint so it pushes a new frame the INSTANT one is produced,
        not after a polling interval. Combined with backpressure-aware
        send, this means the only thing on the wire at any moment is
        the most-recent frame the browser is ready for.
        """
        with self._frame_event:
            ok = self._frame_event.wait_for(
                lambda: (
                    self._latest_frame is not None
                    and self._latest_frame_at > last_frame_at
                ),
                timeout=timeout,
            )
            if not ok or self._latest_frame is None:
                return None
            return (
                self._latest_frame.copy(),
                list(self._latest_detections),
                self._latest_frame_at,
            )

    def run(self) -> None:
        # Worker is now EVENT-DRIVEN: it blocks on the drain thread's
        # Condition variable, waking up the instant a new frame is
        # published. NO fixed-pace sleep, NO polling — the producer→
        # consumer latency drops to ~1 ms (just OS scheduling).
        #
        # The previous version slept `pace = 1/fps_effective` between
        # iterations to avoid CPU spin. That worked but added up to one
        # full frame interval (50-66 ms at 15-20 fps) of avoidable
        # latency to the live preview. With the Condition wait, the
        # worker wakes from inside the drain thread's notify_all()
        # within microseconds.
        #
        # Detection is still rate-limited to 1 Hz internally — we just
        # don't gate the FAST path on a timer anymore.
        last_detection_at = 0.0
        last_processed_ts = 0.0
        # Single-slot handoff from the fast loop to the detection thread.
        # The fast loop sets the LATEST (frame, ts) ready for detection;
        # the detection thread picks it up when it's ready. Single-slot
        # means a slow detection pass NEVER backlogs — only the freshest
        # frame is ever inspected for faces. ms-level latency.
        pending_for_detection: dict = {"frame": None, "ts": 0.0}
        pending_lock = threading.Lock()
        pending_cv = threading.Condition(pending_lock)

        def _detection_loop() -> None:
            """Runs in its own thread. Picks up the freshest frame from
            pending_for_detection, runs InsightFace, drives the attendance
            pipeline. The MAIN worker loop never waits on detection — it
            keeps publishing frames to the live preview at the camera's
            native rate."""
            local_last_at = 0.0
            while not self._stop_event.is_set():
                with pending_cv:
                    pending_cv.wait_for(
                        lambda: (
                            pending_for_detection["frame"] is not None
                            and pending_for_detection["ts"] > local_last_at
                        ) or self._stop_event.is_set(),
                        timeout=1.0,
                    )
                    if self._stop_event.is_set():
                        return
                    frame = pending_for_detection["frame"]
                    ts = pending_for_detection["ts"]
                    if frame is None or ts <= local_last_at:
                        continue
                    # Don't .copy(): the fast loop publishes via
                    # _set_latest_frame_only which copies into its own
                    # slot. The reference we hold here is exclusive to
                    # this thread until the next handoff.
                    local_last_at = ts
                try:
                    self._run_detection_cycle(frame)
                except Exception:
                    log.exception(
                        "[%s] detection cycle crashed", self.camera_name
                    )

        det_thread = threading.Thread(
            target=_detection_loop,
            name=f"detect[{self.camera_name}]",
            daemon=True,
        )
        det_thread.start()

        log.info(
            "[%s] worker starting (type=%s, native_fps=%d, mode=fast+detect-thread)",
            self.camera_name,
            self.camera_type.value,
            self._effective_fps(),
        )

        # Periodic fps self-report. Every 30s the worker logs its own
        # actual processing rate vs expected, with a WARNING if drift is
        # significant. This is the in-process counterpart to the health
        # endpoint's per-camera degraded check — operators tailing the
        # log see drift before any external monitor would. Critical: the
        # log line below is what would have caught the audit's blocking-
        # result() regression in seconds instead of waiting for someone
        # to notice the live tile says "Reconnecting".
        next_perf_log_at = time.monotonic() + 30.0
        perf_log_baseline_frames = 0

        while not self._stop_event.is_set():
            # Block until the drain thread publishes a frame newer than
            # the last one we processed. 1s timeout so we can re-check
            # the stop event and the reader's health periodically.
            result = self.reader.wait_next_drained_frame(
                last_processed_ts, timeout=1.0
            )
            if self._stop_event.is_set():
                break
            now = time.monotonic()
            if now >= next_perf_log_at:
                window_frames = self.stats.processed_frames - perf_log_baseline_frames
                window_seconds = now - (next_perf_log_at - 30.0)
                actual_fps = window_frames / max(1e-3, window_seconds)
                expected_fps = self._effective_fps()
                ratio = actual_fps / max(1, expected_fps)
                if ratio < 0.5 and window_seconds > 5:
                    log.warning(
                        "[%s] performance DEGRADED: %.1f fps actual vs %d fps expected "
                        "(%.0f%% of target) over last %.0fs — detection or drain stall?",
                        self.camera_name, actual_fps, expected_fps,
                        ratio * 100, window_seconds,
                    )
                else:
                    log.debug(
                        "[%s] perf: %.1f fps actual vs %d expected (%.0f%%)",
                        self.camera_name, actual_fps, expected_fps, ratio * 100,
                    )
                perf_log_baseline_frames = self.stats.processed_frames
                next_perf_log_at = now + 30.0

            try:
                if result is None:
                    # Drain thread had no fresh frame within timeout —
                    # camera is reconnecting or dead. Run a regular
                    # reader.read() to surface the reader's diagnostic
                    # to the worker's stats (last_error, etc).
                    frame = self.reader.read()
                else:
                    frame, last_processed_ts = result
                self.stats.last_heartbeat = time.monotonic()
                # Always sync reader-side counters to stats so the UI sees them,
                # whether or not we got a frame this tick.
                self.stats.consecutive_open_failures = self.reader.consecutive_open_failures
                self.stats.consecutive_read_failures = self.reader.consecutive_read_failures
                self.stats.total_reconnects = self.reader.total_reconnects
                self.stats.health_state = self.reader.health_state
                if frame is None:
                    # Surface the reader's diagnostic so admins know WHY there's
                    # no frame (URL wrong, creds wrong, port closed, codec, etc).
                    reader_err = self.reader.last_error
                    if reader_err and reader_err != self.stats.last_error:
                        self.stats.last_error = reader_err
                        self.stats.last_error_at = time.monotonic()
                    continue
                # Got a frame — clear stale errors so the UI doesn't show
                # last week's outage forever.
                if self.stats.last_error is not None:
                    self.stats.last_error = None
                    self.stats.last_error_at = None

                # ---------- FAST PATH: keep preview smooth ----------
                # Update the frame immediately so the live preview always
                # reflects the camera's most recent image. We re-use the
                # previous detections (drawn on this newer frame) until the
                # next detection cycle finishes.
                self._set_latest_frame_only(frame)
                self.stats.processed_frames += 1

                # ---------- SLOW PATH HANDOFF — non-blocking ----------
                # We DON'T run detection inline anymore (that would block
                # the fast frame-publish loop for ~500ms per detection
                # cycle, capping the live preview at ~2 fps). Instead the
                # detection thread picks up the latest frame and runs
                # InsightFace + recognition + attendance in the
                # background. The fast loop returns to consuming the next
                # drain frame immediately. Live preview keeps up with the
                # camera's native 20fps regardless of detection cost.
                if (now - last_detection_at) >= _DETECTION_INTERVAL_SECONDS:
                    last_detection_at = now
                    with pending_cv:
                        # Single-slot overwrite: if a previous detection
                        # cycle is still running, the new frame replaces
                        # the pending one. Only the FRESHEST frame is
                        # ever inspected — never a backlog.
                        pending_for_detection["frame"] = frame
                        pending_for_detection["ts"] = last_processed_ts or now
                        pending_cv.notify_all()
            except Exception as exc:
                self.stats.last_error = str(exc)
                self.stats.last_error_at = time.monotonic()
                log.exception("[%s] worker loop error", self.camera_name)
                self._stop_event.wait(1.0)

        # Wake the detection thread so it sees stop_event and exits.
        with pending_cv:
            pending_cv.notify_all()
        det_thread.join(timeout=2.0)
        self.reader.stop()
        log.info("[%s] worker stopped", self.camera_name)

    def _run_detection_cycle(self, frame: np.ndarray) -> None:
        """The slow path — detect, recognize, drive attendance pipeline.

        Called from a dedicated detection thread so the worker's fast
        frame-publish loop is never blocked. Detection results are
        written to the latest-detections slot via _set_latest_detections,
        which the WS/MJPEG preview reads when it next publishes a frame.
        """
        # Use the bounded thread pool to cap GLOBAL concurrent InsightFace
        # inferences (across all cameras). FaceService still serializes
        # access to the onnx model via its own lock; the pool just makes
        # sure 4 cameras don't all queue up at the same lock.
        future = _get_detection_pool().submit(
            self.face_service.detect, frame
        )
        faces = future.result()

        results: list[tuple[DetectedFace, MatchResult]] = []
        detections: list[FrameDetection] = []
        for face in faces:
            match = self.recognition.match(face.embedding)
            results.append((face, match))
            detections.append(self._face_to_detection(face, match))

        # Sync the detections to the latest frame so the preview overlay
        # updates the moment a new face is found / lost.
        self._set_latest_detections(detections)
        if not faces:
            return

        log.info(
            "[%s] detected %d face(s) — %s",
            self.camera_name,
            len(faces),
            ", ".join(f"{d.label}({d.score:.2f})" for d in detections),
        )

        now = time.monotonic()
        for face, match in results:
            if match.employee_id is None:
                self._maybe_capture_unknown(face=face, frame=frame)
                continue
            if not self.cooldown.allow(match.employee_id):
                continue
            try:
                with session_scope() as db:
                    service = AttendanceService(db)
                    outcome = service.process_auto_event(
                        employee_id=match.employee_id,
                        camera_id=self.camera_id,
                        camera_type=self.camera_type,
                        confidence=match.score,
                        frame_bgr=frame,
                        bbox=face.bbox,
                        at_time=now_utc(),
                    )
                if outcome.created:
                    self.stats.events_generated += 1
                    self._maybe_auto_enroll(match.employee_id, frame, match.score)
                else:
                    self.cooldown.reset(match.employee_id)
                    log.debug(
                        "[%s] event skipped emp=%s reason=%s",
                        self.camera_name,
                        match.employee_id,
                        outcome.reason,
                    )
            except Exception as exc:
                self.cooldown.reset(match.employee_id)
                self.stats.last_error = f"attendance: {exc}"
                self.stats.last_error_at = now
                log.exception("[%s] attendance pipeline error", self.camera_name)

    def _face_to_detection(
        self, face: DetectedFace, match: MatchResult
    ) -> FrameDetection:
        """Pair a detected face with its recognition result for the
        preview overlay. Looks up the employee's display name from the
        embedding cache (cheap — small in-memory list).
        """
        if match.employee_id is None:
            return FrameDetection(
                bbox=face.bbox,
                label="Unknown",
                score=float(match.score),
                matched=False,
            )
        name = "Employee"
        _, _, entries = self.embedding_cache.snapshot()
        for entry in entries:
            if entry.employee_id == match.employee_id:
                name = entry.employee_name
                break
        return FrameDetection(
            bbox=face.bbox,
            label=name,
            score=float(match.score),
            matched=True,
        )

    def _maybe_capture_unknown(
        self, *, face, frame: np.ndarray
    ) -> None:
        """Persist an unknown-face capture if the pipeline is enabled.

        Cheap kill-switch check first to avoid opening a DB session on every
        unrecognized face when the feature is off (the typical state).
        Errors here never propagate — the recognition loop must keep running.
        """
        if not get_settings_service().get().unknown_capture_enabled:
            return
        try:
            with session_scope() as db:
                outcome = UnknownCaptureService(db).maybe_capture(
                    face=face,
                    frame_bgr=frame,
                    camera_id=self.camera_id,
                    captured_at=now_utc(),
                )
            if outcome.accepted:
                self.stats.unknown_captures += 1
                log.info(
                    "[%s] unknown captured cluster_id=%s new=%s",
                    self.camera_name,
                    outcome.cluster_id,
                    outcome.cluster_was_new,
                )
            else:
                self.stats.unknown_skipped += 1
                # Promoted from DEBUG to INFO so admins can see why faces
                # are being filtered without enabling debug logging
                # everywhere — drop back to DEBUG once tuning is settled.
                log.info(
                    "[%s] unknown skipped reason=%s",
                    self.camera_name,
                    outcome.reason,
                )
        except Exception:
            self.stats.last_error = "unknown_capture_pipeline"
            log.exception(
                "[%s] unknown capture pipeline error", self.camera_name
            )

    def _maybe_auto_enroll(
        self, employee_id: int, frame: np.ndarray, match_score: float
    ) -> None:
        s = get_settings_service().get()
        if not s.auto_update_enabled or match_score < s.auto_update_threshold:
            return
        try:
            with session_scope() as db:
                added = TrainingService(
                    db, self.face_service, self.embedding_cache
                ).auto_enroll_from_frame(
                    employee_id=employee_id,
                    frame_bgr=frame,
                    match_score=match_score,
                )
            if added:
                self.stats.auto_enrollments += 1
        except Exception:
            log.exception("[%s] auto-enroll raised unexpectedly", self.camera_name)
