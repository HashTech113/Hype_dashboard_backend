from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logger import get_logger
from app.db.session import session_scope
from app.repositories.camera_repo import CameraRepository
from app.services.cooldown_service import get_cooldown_service
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.workers.camera_worker import CameraWorker

log = get_logger(__name__)


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

    def _build_worker(self, camera) -> CameraWorker:  # type: ignore[no-untyped-def]
        return CameraWorker(
            camera_id=camera.id,
            camera_name=camera.name,
            rtsp_url=camera.rtsp_url,
            camera_type=camera.camera_type,
            face_service=self._face_service,
            embedding_cache=self._embedding_cache,
            cooldown_service=self._cooldown,
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

    def restart(self, camera_id: int) -> None:
        with session_scope() as db:
            cam = CameraRepository(db).get(camera_id)
            if cam is None:
                raise NotFoundError(f"Camera {camera_id} not found")
            cam_snapshot = (cam.id, cam.name, cam.rtsp_url, cam.camera_type, cam.is_active)

        with self._lock:
            existing = self._workers.pop(camera_id, None)
        if existing is not None:
            existing.stop()
            existing.join(timeout=5.0)

        if not cam_snapshot[4]:
            log.info("Camera id=%s is inactive; not restarting", camera_id)
            return

        class _Shim:
            def __init__(self, data):
                self.id, self.name, self.rtsp_url, self.camera_type, self.is_active = data

        worker = self._build_worker(_Shim(cam_snapshot))
        worker.start()
        with self._lock:
            self._workers[camera_id] = worker
        log.info("Restarted worker for camera id=%s", camera_id)

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
        """Fetch the latest frame from a camera worker, optionally draw
        bounding boxes for the most recent detections, and return JPEG
        bytes. Returns None if the camera has no recent frame.
        """
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None or not worker.is_running:
            return None
        snapshot = worker.get_latest_preview(max_age_seconds=max_age_seconds)
        if snapshot is None:
            return None
        # Lazy import — keeps cv2 cost off the hot lifespan-startup path
        from app.services.preview_service import annotate_frame, encode_jpeg

        frame, detections = snapshot
        if annotated and detections:
            frame = annotate_frame(frame, detections)
        return encode_jpeg(frame, quality=quality)

    def status(self) -> list[dict]:
        out: list[dict] = []
        with self._lock:
            workers = dict(self._workers)
        for cam_id, w in workers.items():
            out.append(
                {
                    "camera_id": cam_id,
                    "camera_name": w.camera_name,
                    "is_running": w.is_running,
                    "last_heartbeat_age_seconds": w.last_heartbeat_age_seconds,
                    "last_frame_age_seconds": w.last_frame_age_seconds,
                    "processed_frames": w.stats.processed_frames,
                    "events_generated": w.stats.events_generated,
                    "auto_enrollments": w.stats.auto_enrollments,
                    "unknown_captures": w.stats.unknown_captures,
                    "unknown_skipped": w.stats.unknown_skipped,
                    "last_error": w.stats.last_error,
                    "last_heartbeat": datetime.now(tz=timezone.utc),
                }
            )
        return out

    def _health_loop(self) -> None:
        settings = get_settings()
        while not self._stop_health.wait(settings.CAMERA_HEALTH_INTERVAL_SECONDS):
            try:
                with self._lock:
                    items = list(self._workers.items())
                for cam_id, worker in items:
                    if not worker.is_alive():
                        log.warning("Worker for camera id=%s died; restarting", cam_id)
                        self.restart(cam_id)
                        continue
                    age = worker.last_heartbeat_age_seconds
                    if age > settings.CAMERA_HEARTBEAT_TIMEOUT_SECONDS:
                        log.warning(
                            "Worker for camera id=%s stale (age=%.1fs); restarting",
                            cam_id,
                            age,
                        )
                        self.restart(cam_id)
            except Exception:
                log.exception("Camera health loop error")
