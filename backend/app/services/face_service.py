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
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._app: FaceAnalysis | None = None
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
            self._app = app
            self._loaded = True
            log.info(
                "InsightFace '%s' loaded (provider=%s, det=%d)",
                settings.FACE_MODEL_NAME,
                settings.FACE_PROVIDER,
                settings.FACE_DET_SIZE,
            )

    def _ensure_loaded(self) -> FaceAnalysis:
        if not self._loaded or self._app is None:
            self.load()
        assert self._app is not None
        return self._app

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
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
