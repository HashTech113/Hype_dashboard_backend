"""Unknown-face capture pipeline.

Invoked by camera workers when `RecognitionService.match()` returns no
employee match. Decides whether to keep the face, which cluster (unique
person) it belongs to, and persists a face crop + capture row + updated
centroid.

Design — see `memory/project_unknown_faces.md` for the full rationale:

  * Embeddings are stored as L2-normalized float32 (512-d) byte buffers,
    matching `EmployeeFaceEmbedding.vector` precision exactly.
  * Online clustering: cosine similarity between the new face's embedding
    and every PENDING cluster's stored centroid; first centroid above
    `unknown_cluster_match_threshold` (sorted by recency) wins.
  * Centroid maintenance: recomputed from the cluster's KEEP captures on
    each insert (mean → re-normalize). Bounded by `PER_CLUSTER_KEEP_CAP`,
    so the recompute is O(30) numpy ops — cheaper than incremental
    accumulators with their normalization-drift risk.
  * Per-cluster cooldown is in-process (single backend process); HDBSCAN
    re-clustering (Module 5) heals any concurrent double-create.
  * Quality gate runs first so junk frames never anchor a centroid.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import UnknownCaptureStatus, UnknownClusterStatus
from app.core.logger import get_logger
from app.models.unknown_face import UnknownFaceCapture, UnknownFaceCluster
from app.repositories.unknown_capture_repo import UnknownCaptureRepository
from app.repositories.unknown_cluster_repo import UnknownClusterRepository
from app.services.face_service import DetectedFace
from app.services.settings_service import get_settings_service
from app.utils.face_quality import (
    FaceQualityMetrics,
    QualityThresholds,
    measure_and_evaluate,
)
from app.utils.image_utils import crop_bbox, write_jpeg
from app.utils.time_utils import to_local

log = get_logger(__name__)

_EMBEDDING_DIM = 512
_PER_CLUSTER_KEEP_CAP = 30  # max KEEP captures per cluster; oldest demoted to DISCARDED
_CROP_PAD_RATIO = 0.25  # context around the face on disk, mirrors snapshot service
_JPEG_QUALITY = 88


@dataclass(frozen=True)
class UnknownCaptureOutcome:
    accepted: bool
    reason: str  # "ok" | "disabled" | "quality:<tag>" | "cooldown" | "error:<msg>"
    cluster_id: int | None
    capture_id: int | None
    cluster_was_new: bool
    match_score: float
    metrics: FaceQualityMetrics | None


class UnknownCaptureService:
    """Persists unknown-face captures and maintains their cluster assignments.

    Construct one per DB session (same pattern as `AttendanceService`).
    Cooldown bookkeeping is class-level so it survives across instances and
    is shared by every camera worker thread.
    """

    _cooldown_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_capture_monotonic: ClassVar[dict[int, float]] = {}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cluster_repo = UnknownClusterRepository(db)
        self.capture_repo = UnknownCaptureRepository(db)
        env = get_settings()
        self._model_name = env.FACE_MODEL_NAME
        self._unknowns_dir = Path(env.UNKNOWNS_DIR)

    # ------------------------------------------------------------------
    # Public entry point — called by the camera worker
    # ------------------------------------------------------------------

    def maybe_capture(
        self,
        *,
        face: DetectedFace,
        frame_bgr: np.ndarray,
        camera_id: int | None,
        captured_at: datetime,
    ) -> UnknownCaptureOutcome:
        """Try to capture an unknown face.

        Returns a `UnknownCaptureOutcome` for predictable, non-error rejects
        (disabled / quality fail / cooldown / malformed embedding). Lets
        infrastructure errors (DB, disk I/O) propagate so the caller's
        unit-of-work can roll back — the camera worker's outer `try/except`
        catches them and increments `last_error` instead of corrupting the
        session.

        Steps: kill-switch → quality gate → cluster match → cooldown gate
        → persist (cluster row if new, JPG, capture row, centroid).
        """
        return self._process(
            face=face,
            frame_bgr=frame_bgr,
            camera_id=camera_id,
            captured_at=captured_at,
        )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _process(
        self,
        *,
        face: DetectedFace,
        frame_bgr: np.ndarray,
        camera_id: int | None,
        captured_at: datetime,
    ) -> UnknownCaptureOutcome:
        settings = get_settings_service().get()
        if not settings.unknown_capture_enabled:
            return UnknownCaptureOutcome(
                False, "disabled", None, None, False, 0.0, None
            )

        # 1) Quality gate ------------------------------------------------
        thresholds = QualityThresholds(
            min_face_size_px=settings.unknown_min_face_size_px,
            min_det_score=settings.unknown_min_face_quality,
            min_sharpness=settings.unknown_min_sharpness,
        )
        verdict = measure_and_evaluate(
            frame_bgr=frame_bgr,
            bbox=face.bbox,
            kps=face.kps,
            det_score=face.det_score,
            thresholds=thresholds,
        )
        if not verdict.accepted:
            return UnknownCaptureOutcome(
                False,
                f"quality:{verdict.reason}",
                None,
                None,
                False,
                0.0,
                verdict.metrics,
            )

        # 2) Normalize embedding -----------------------------------------
        emb = self._normalize(face.embedding)
        if emb is None:
            return UnknownCaptureOutcome(
                False, "error:zero_norm_embedding", None, None, False, 0.0, verdict.metrics
            )

        # 3) Find best matching PENDING cluster --------------------------
        match_id, match_score = self._find_best_match(
            emb, settings.unknown_cluster_match_threshold
        )

        cluster_was_new = False
        if match_id is None:
            # New unique person — create a fresh cluster
            cluster = self._create_cluster(
                emb=emb, captured_at=captured_at
            )
            cluster_was_new = True
        else:
            cluster = self.cluster_repo.get(match_id)
            if cluster is None:
                # Race: cluster was removed between match and load. Fall back
                # to a fresh cluster so we don't drop the face.
                cluster = self._create_cluster(emb=emb, captured_at=captured_at)
                cluster_was_new = True

        # 4) Per-cluster cooldown ---------------------------------------
        if not cluster_was_new and not self._cooldown_allow(
            cluster.id, settings.unknown_capture_cooldown_seconds
        ):
            return UnknownCaptureOutcome(
                False,
                "cooldown",
                cluster.id,
                None,
                False,
                match_score,
                verdict.metrics,
            )

        # 5) Crop + write JPEG ------------------------------------------
        out_path = self._build_path(cluster.id, captured_at)
        crop = crop_bbox(frame_bgr, face.bbox, pad=_CROP_PAD_RATIO)
        if crop.size == 0:
            crop = frame_bgr  # safety fallback for degenerate bbox
        write_jpeg(out_path, crop, quality=_JPEG_QUALITY)

        # 6) Insert capture row -----------------------------------------
        x1, y1, x2, y2 = face.bbox
        capture = UnknownFaceCapture(
            cluster_id=cluster.id,
            file_path=str(out_path),
            embedding=emb.tobytes(),
            embedding_dim=int(emb.size),
            model_name=self._model_name,
            camera_id=camera_id,
            bbox_x=int(x1),
            bbox_y=int(y1),
            bbox_w=int(x2 - x1),
            bbox_h=int(y2 - y1),
            det_score=float(face.det_score),
            sharpness_score=float(verdict.metrics.sharpness),
            captured_at=captured_at,
            status=UnknownCaptureStatus.KEEP,
        )
        self.capture_repo.add(capture)

        # 7) Per-cluster cap — demote oldest KEEP if over cap ------------
        self._enforce_per_cluster_cap(cluster.id)

        # 8) Recompute centroid + counters -------------------------------
        new_centroid, new_count = self._recompute_centroid(cluster.id)
        if new_centroid is not None:
            self.cluster_repo.update_after_capture(
                cluster,
                new_centroid=new_centroid.tobytes(),
                new_centroid_dim=int(new_centroid.size),
                new_member_count=new_count,
                last_seen_at=captured_at,
            )

        # 9) Bookkeeping -------------------------------------------------
        self._cooldown_set(cluster.id)

        log.info(
            "Unknown captured cluster_id=%s capture_id=%s new=%s match_score=%.3f cam=%s",
            cluster.id,
            capture.id,
            cluster_was_new,
            match_score,
            camera_id,
        )
        return UnknownCaptureOutcome(
            accepted=True,
            reason="ok",
            cluster_id=cluster.id,
            capture_id=capture.id,
            cluster_was_new=cluster_was_new,
            match_score=match_score,
            metrics=verdict.metrics,
        )

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _find_best_match(
        self, query: np.ndarray, threshold: float
    ) -> tuple[int | None, float]:
        """Return `(cluster_id, score)` of the best-matching PENDING cluster
        whose centroid cosine-similarity with `query` is >= `threshold`. If
        nothing meets the bar, returns `(None, best_score_seen)`.
        """
        rows = self.cluster_repo.list_active_centroids(model_name=self._model_name)
        if not rows:
            return None, 0.0

        ids: list[int] = []
        vectors: list[np.ndarray] = []
        for cid, blob, dim in rows:
            try:
                vec = np.frombuffer(blob, dtype=np.float32)
                if vec.size != dim or vec.size != _EMBEDDING_DIM:
                    log.warning(
                        "Cluster %s has malformed centroid (dim=%s, size=%s); skipping",
                        cid,
                        dim,
                        vec.size,
                    )
                    continue
                ids.append(cid)
                vectors.append(vec)
            except ValueError:
                log.warning("Cluster %s has unreadable centroid; skipping", cid)
                continue

        if not vectors:
            return None, 0.0

        matrix = np.vstack(vectors).astype(np.float32)
        # `query` is unit-norm; matrix rows are unit-norm by construction.
        sims = matrix @ query
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])
        if best_score < threshold:
            return None, best_score
        return int(ids[best_idx]), best_score

    # ------------------------------------------------------------------
    # Cluster lifecycle
    # ------------------------------------------------------------------

    def _create_cluster(
        self, *, emb: np.ndarray, captured_at: datetime
    ) -> UnknownFaceCluster:
        cluster = UnknownFaceCluster(
            label=None,
            centroid=emb.tobytes(),
            centroid_dim=int(emb.size),
            model_name=self._model_name,
            member_count=0,  # set by recompute after capture insert
            first_seen_at=captured_at,
            last_seen_at=captured_at,
            status=UnknownClusterStatus.PENDING,
        )
        self.db.add(cluster)
        self.db.flush()  # need cluster.id before path/insert
        return cluster

    def _enforce_per_cluster_cap(self, cluster_id: int) -> None:
        """If the cluster has more than `_PER_CLUSTER_KEEP_CAP` KEEP captures
        after this insert, demote the oldest KEEP to DISCARDED. Files stay on
        disk so admins can still inspect them; only the centroid stops being
        anchored by them.
        """
        count = self.capture_repo.count_keep_for_cluster(cluster_id)
        if count <= _PER_CLUSTER_KEEP_CAP:
            return
        oldest = self.capture_repo.get_oldest_keep(cluster_id)
        if oldest is None:
            return
        oldest.status = UnknownCaptureStatus.DISCARDED
        self.db.flush()
        log.debug(
            "Cluster %s over cap (%d > %d); demoted capture id=%s",
            cluster_id,
            count,
            _PER_CLUSTER_KEEP_CAP,
            oldest.id,
        )

    def _recompute_centroid(
        self, cluster_id: int
    ) -> tuple[np.ndarray | None, int]:
        """Recompute the cluster centroid as the L2-normalized mean of its
        KEEP capture embeddings. Returns `(centroid, member_count)`. If the
        cluster is empty (every capture got demoted), returns `(None, 0)`.
        """
        rows = self.capture_repo.list_keep_embeddings_for_cluster(cluster_id)
        if not rows:
            return None, 0
        vectors: list[np.ndarray] = []
        for blob, dim in rows:
            arr = np.frombuffer(blob, dtype=np.float32)
            if arr.size != dim or arr.size != _EMBEDDING_DIM:
                continue
            vectors.append(arr)
        if not vectors:
            return None, 0
        mat = np.vstack(vectors).astype(np.float32)
        mean = mat.mean(axis=0)
        n = float(np.linalg.norm(mean))
        if n <= 0.0:
            return None, len(vectors)
        return (mean / n).astype(np.float32), len(vectors)

    # ------------------------------------------------------------------
    # Cooldown (process-wide, per cluster)
    # ------------------------------------------------------------------

    def _cooldown_allow(self, cluster_id: int, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0:
            return True
        now = time.monotonic()
        with self._cooldown_lock:
            last = self._last_capture_monotonic.get(cluster_id)
            return last is None or (now - last) >= float(cooldown_seconds)

    def _cooldown_set(self, cluster_id: int) -> None:
        now = time.monotonic()
        with self._cooldown_lock:
            self._last_capture_monotonic[cluster_id] = now

    @classmethod
    def reset_cooldown(cls, cluster_id: int) -> None:
        """Drop a cluster's cooldown timestamp — used after retention purge or
        when a cluster is promoted/discarded so its id won't leak memory.
        """
        with cls._cooldown_lock:
            cls._last_capture_monotonic.pop(cluster_id, None)

    @classmethod
    def clear_cooldowns(cls) -> None:
        with cls._cooldown_lock:
            cls._last_capture_monotonic.clear()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray | None:
        v = np.asarray(vec, dtype=np.float32).ravel()
        if v.size != _EMBEDDING_DIM:
            return None
        n = float(np.linalg.norm(v))
        if n <= 0.0:
            return None
        return (v / n).astype(np.float32)

    def _build_path(self, cluster_id: int, captured_at: datetime) -> Path:
        local_ts = to_local(captured_at)
        filename = f"{local_ts.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
        return self._unknowns_dir / f"cluster_{cluster_id}" / filename
