from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from insightface.app import FaceAnalysis

from app.config import get_settings
from app.core.exceptions import FaceRecognitionError
from app.core.logger import get_logger
from app.services.settings_service import get_settings_service

log = get_logger(__name__)


@dataclass(frozen=True)
class DetectedFace:
    bbox: tuple[int, int, int, int]
    embedding: np.ndarray  # L2-normalized buffalo_l vector, dim=512
    det_score: float
    kps: np.ndarray  # 5 landmarks (left_eye, right_eye, nose, l_mouth, r_mouth), shape (5, 2)


class FaceService:
    """Thread-safe wrapper around InsightFace FaceAnalysis.

    THREAD-SAFETY CONTRACT (read before modifying this class):
    ---------------------------------------------------------
    The underlying ``insightface.app.FaceAnalysis`` instance is NOT thread-safe.
    Concurrent calls into ``FaceAnalysis.get()`` (or any of its sub-models like
    ``det_model`` / ``rec_model``) from multiple threads will corrupt internal
    ONNX Runtime / numpy buffers and silently produce wrong embeddings or crash.

    In this codebase the model is shared between:
      * Multiple camera worker threads (one per RTSP stream)
      * The HTTP/training thread (enrollment, embedding refresh)
      * The preview / snapshot endpoints

    To prevent the race, ALL access to the underlying model MUST go through
    ``detect()`` / ``detect_single()``, which hold ``self._lock`` for the full
    duration of the inference call.

    DO NOT:
      * Access ``self._app`` directly from outside this class.
      * Add a new method that calls ``self._app.get(...)`` without
        ``with self._lock:`` around the call.
      * Expose ``self._app`` via a public attribute, property, or return value.
      * Use ``_ensure_loaded()`` to obtain a handle and then run inference
        outside the lock — ``_ensure_loaded()`` is for internal use only and
        the returned reference must be used INSIDE ``with self._lock:``.

    If you need a new inference operation, add a method here that follows the
    same ``with self._lock: ... app.get(...) ...`` pattern used by ``detect()``.
    """

    # Name-mangled (double underscore) so external code cannot reach the model
    # via ``service._app``. Only methods defined inside ``FaceService`` can
    # resolve ``self.__app`` (Python rewrites it to ``_FaceService__app``).
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.__app: FaceAnalysis | None = None
        self._loaded = False

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            settings = get_settings()
            providers = [settings.FACE_PROVIDER]
            try:
                app = FaceAnalysis(
                    name=settings.FACE_MODEL_NAME,
                    root=settings.FACE_MODEL_ROOT,
                    providers=providers,
                )
                app.prepare(ctx_id=0, det_size=(settings.FACE_DET_SIZE, settings.FACE_DET_SIZE))
            except Exception as exc:
                log.exception("Failed to initialize InsightFace model")
                raise FaceRecognitionError(f"Face model init failed: {exc}") from exc
            self.__app = app
            self._loaded = True
            log.info(
                "InsightFace '%s' loaded (provider=%s, det=%d)",
                settings.FACE_MODEL_NAME,
                settings.FACE_PROVIDER,
                settings.FACE_DET_SIZE,
            )

    def _ensure_loaded(self) -> FaceAnalysis:
        """Internal: return the underlying model handle.

        WARNING: The returned ``FaceAnalysis`` is NOT thread-safe. Callers MUST
        invoke it only while holding ``self._lock``. Do not return this handle
        to any code outside ``FaceService``.
        """
        if not self._loaded or self.__app is None:
            self.load()
        assert self.__app is not None
        return self.__app

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        # NOTE: ``app.get()`` MUST run inside the lock — InsightFace is not
        # thread-safe. See class docstring for the full contract.
        app = self._ensure_loaded()
        with self._lock:
            raw = app.get(frame_bgr)
        out: list[DetectedFace] = []
        for f in raw:
            emb = getattr(f, "normed_embedding", None)
            kps = getattr(f, "kps", None)
            if emb is None or kps is None:
                continue
            bbox = f.bbox.astype(int).tolist()
            out.append(
                DetectedFace(
                    bbox=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                    embedding=np.asarray(emb, dtype=np.float32),
                    det_score=float(getattr(f, "det_score", 0.0)),
                    kps=np.asarray(kps, dtype=np.float32),
                )
            )
        return out

    def detect_single(self, frame_bgr: np.ndarray) -> DetectedFace:
        min_quality = get_settings_service().get().face_min_quality
        faces = self.detect(frame_bgr)
        if not faces:
            raise FaceRecognitionError("No face detected")
        if len(faces) > 1:
            faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
        best = faces[0]
        if best.det_score < min_quality:
            raise FaceRecognitionError(
                f"Face quality too low ({best.det_score:.2f} < {min_quality})"
            )
        return best
