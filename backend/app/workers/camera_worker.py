from __future__ import annotations

import threading
import time
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
_DETECTION_INTERVAL_SECONDS: float = 0.5  # 2 detections/sec per camera


@dataclass
class WorkerStats:
    processed_frames: int = 0
    events_generated: int = 0
    auto_enrollments: int = 0
    unknown_captures: int = 0
    unknown_skipped: int = 0
    last_heartbeat: float = field(default_factory=time.monotonic)
    last_error: str | None = None


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
    ) -> None:
        super().__init__(name=f"cam-{camera_id}-{camera_name}", daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.camera_type = camera_type
        self.face_service = face_service
        self.embedding_cache = embedding_cache
        self.cooldown = cooldown_service
        self.recognition = RecognitionService(embedding_cache)
        self.reader = RTSPReader(rtsp_url, name=camera_name)
        self._stop_event = threading.Event()
        self.stats = WorkerStats()

        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._latest_frame_at: float = 0.0
        self._latest_detections: list[FrameDetection] = []

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

    def _set_latest_frame(
        self,
        frame: np.ndarray,
        detections: list[FrameDetection] | None = None,
    ) -> None:
        """Replace both frame and detections. Used when detection ran for this
        frame (so the boxes are exactly synced to it).
        """
        with self._frame_lock:
            self._latest_frame = frame.copy()
            self._latest_frame_at = time.monotonic()
            self._latest_detections = list(detections or [])

    def _set_latest_frame_only(self, frame: np.ndarray) -> None:
        """Update just the frame (preserve last detections) — fast path
        used to keep the live preview at the camera's read rate even when
        face detection is rate-limited to a lower cadence.

        Detections from up to ~_DETECTION_INTERVAL_SECONDS ago are still
        drawn on the new frame. Box positions visibly lag the face by the
        detection interval; this is the standard trade-off real CCTV
        previews make and is much better than a stuttering feed.
        """
        with self._frame_lock:
            self._latest_frame = frame.copy()
            self._latest_frame_at = time.monotonic()

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

    def run(self) -> None:
        settings = get_settings_service().get()
        min_interval = 1.0 / max(1, settings.camera_fps)
        next_deadline = time.monotonic()
        last_detection_at = 0.0
        log.info("[%s] worker starting (type=%s)", self.camera_name, self.camera_type.value)

        while not self._stop_event.is_set():
            now = time.monotonic()
            if now < next_deadline:
                self._stop_event.wait(min(0.05, next_deadline - now))
                continue
            # Use current settings each tick so runtime-tuned fps takes effect.
            min_interval = 1.0 / max(1, get_settings_service().get().camera_fps)
            next_deadline = now + min_interval

            try:
                frame = self.reader.read()
                self.stats.last_heartbeat = time.monotonic()
                if frame is None:
                    continue

                # ---------- FAST PATH: keep preview smooth ----------
                # Update the frame immediately so the live preview always
                # reflects the camera's most recent image. We re-use the
                # previous detections (drawn on this newer frame) until the
                # next detection cycle finishes.
                self._set_latest_frame_only(frame)
                self.stats.processed_frames += 1

                # ---------- SLOW PATH: detect + recognize + attend ----------
                # Rate-limited so 4 cameras × heavy InsightFace doesn't
                # choke the CPU. 2 FPS detection per camera is plenty for
                # attendance — the global cooldown dedupes anyway.
                if (now - last_detection_at) < _DETECTION_INTERVAL_SECONDS:
                    continue
                last_detection_at = now

                faces = self.face_service.detect(frame)

                # Run recognition once per face — results feed both the
                # preview overlay AND the attendance pipeline below.
                results: list[tuple[DetectedFace, MatchResult]] = []
                detections: list[FrameDetection] = []
                for face in faces:
                    match = self.recognition.match(face.embedding)
                    results.append((face, match))
                    detections.append(self._face_to_detection(face, match))

                # Sync the detections to the latest frame so the preview
                # overlay updates the moment a new face is found / lost.
                self._set_latest_detections(detections)
                if not faces:
                    continue

                # Diagnostic — temporarily INFO so admins can trace whether
                # InsightFace is finding faces. Faces here have already been
                # gated by `face_min_quality` inside FaceService.detect.
                log.info(
                    "[%s] detected %d face(s) — %s",
                    self.camera_name,
                    len(faces),
                    ", ".join(
                        f"{d.label}({d.score:.2f})" for d in detections
                    ),
                )

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
                        log.exception("[%s] attendance pipeline error", self.camera_name)
            except Exception as exc:
                self.stats.last_error = str(exc)
                log.exception("[%s] worker loop error", self.camera_name)
                self._stop_event.wait(1.0)

        self.reader.stop()
        log.info("[%s] worker stopped", self.camera_name)

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
