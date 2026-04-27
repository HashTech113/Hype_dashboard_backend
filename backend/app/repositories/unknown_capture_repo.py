from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select

from app.core.constants import UnknownCaptureStatus, UnknownClusterStatus
from app.models.unknown_face import UnknownFaceCapture, UnknownFaceCluster
from app.repositories.base_repo import BaseRepository


class UnknownCaptureRepository(BaseRepository[UnknownFaceCapture]):
    model = UnknownFaceCapture

    # ------------------------------------------------------------------
    # Centroid recomputation — pull every KEEP embedding for a cluster
    # ------------------------------------------------------------------

    def list_keep_embeddings_for_cluster(
        self, cluster_id: int
    ) -> list[tuple[bytes, int]]:
        """Return `(embedding_bytes, embedding_dim)` for every KEEP capture in
        the cluster, ordered oldest-first so callers can deterministically
        identify the oldest member when enforcing per-cluster caps.
        """
        stmt = (
            select(UnknownFaceCapture.embedding, UnknownFaceCapture.embedding_dim)
            .where(
                and_(
                    UnknownFaceCapture.cluster_id == cluster_id,
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                )
            )
            .order_by(UnknownFaceCapture.captured_at.asc())
        )
        return [(bytes(r[0]), int(r[1])) for r in self.db.execute(stmt).all()]

    def list_keep_quality_ranked(
        self, cluster_id: int
    ) -> list[UnknownFaceCapture]:
        """Highest-quality KEEP captures first — used by the promotion
        service to pick the best images when training a new employee.
        Ordered by `det_score` desc, then `sharpness_score` desc as a
        tie-break.
        """
        stmt = (
            select(UnknownFaceCapture)
            .where(
                and_(
                    UnknownFaceCapture.cluster_id == cluster_id,
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                )
            )
            .order_by(
                UnknownFaceCapture.det_score.desc(),
                UnknownFaceCapture.sharpness_score.desc(),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_keep_for_cluster(
        self, cluster_id: int, *, order_desc: bool = True
    ) -> list[UnknownFaceCapture]:
        order_col = (
            UnknownFaceCapture.captured_at.desc()
            if order_desc
            else UnknownFaceCapture.captured_at.asc()
        )
        stmt = (
            select(UnknownFaceCapture)
            .where(
                and_(
                    UnknownFaceCapture.cluster_id == cluster_id,
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                )
            )
            .order_by(order_col)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_all_for_cluster(
        self, cluster_id: int
    ) -> list[UnknownFaceCapture]:
        stmt = (
            select(UnknownFaceCapture)
            .where(UnknownFaceCapture.cluster_id == cluster_id)
            .order_by(UnknownFaceCapture.captured_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_oldest_keep(self, cluster_id: int) -> UnknownFaceCapture | None:
        stmt = (
            select(UnknownFaceCapture)
            .where(
                and_(
                    UnknownFaceCapture.cluster_id == cluster_id,
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                )
            )
            .order_by(UnknownFaceCapture.captured_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def count_keep_for_cluster(self, cluster_id: int) -> int:
        stmt = select(func.count(UnknownFaceCapture.id)).where(
            and_(
                UnknownFaceCapture.cluster_id == cluster_id,
                UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_total(self, *, only_keep: bool = False) -> int:
        stmt = select(func.count(UnknownFaceCapture.id))
        if only_keep:
            stmt = stmt.where(UnknownFaceCapture.status == UnknownCaptureStatus.KEEP)
        return int(self.db.execute(stmt).scalar_one())

    def count_older_than(self, cutoff: datetime) -> int:
        stmt = select(func.count(UnknownFaceCapture.id)).where(
            UnknownFaceCapture.captured_at < cutoff
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_keep_in_pending_clusters(
        self, *, model_name: str
    ) -> list[UnknownFaceCapture]:
        """Every KEEP capture from every PENDING cluster — input for the
        global re-cluster pass. Filtered by `model_name` so embeddings
        produced by different recognition models are not mixed.
        """
        stmt = (
            select(UnknownFaceCapture)
            .join(
                UnknownFaceCluster,
                UnknownFaceCluster.id == UnknownFaceCapture.cluster_id,
            )
            .where(
                and_(
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                    UnknownFaceCluster.status == UnknownClusterStatus.PENDING,
                    UnknownFaceCapture.model_name == model_name,
                )
            )
            .order_by(
                UnknownFaceCapture.cluster_id.asc(),
                UnknownFaceCapture.captured_at.asc(),
            )
        )
        return list(self.db.execute(stmt).scalars().all())
