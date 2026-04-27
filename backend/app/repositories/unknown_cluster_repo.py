from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import and_, func, select

from app.core.constants import UnknownCaptureStatus, UnknownClusterStatus
from app.models.unknown_face import UnknownFaceCapture, UnknownFaceCluster
from app.repositories.base_repo import BaseRepository


class UnknownClusterRepository(BaseRepository[UnknownFaceCluster]):
    model = UnknownFaceCluster

    # ------------------------------------------------------------------
    # Lookups for online matching
    # ------------------------------------------------------------------

    def list_active_centroids(
        self, *, model_name: str
    ) -> list[tuple[int, bytes, int]]:
        """Return `(id, centroid_bytes, centroid_dim)` for every PENDING cluster
        that uses the given embedding model. Sorted by `last_seen_at` desc so
        more-recently-active clusters are evaluated first.
        """
        stmt = (
            select(
                UnknownFaceCluster.id,
                UnknownFaceCluster.centroid,
                UnknownFaceCluster.centroid_dim,
            )
            .where(
                and_(
                    UnknownFaceCluster.status == UnknownClusterStatus.PENDING,
                    UnknownFaceCluster.model_name == model_name,
                )
            )
            .order_by(UnknownFaceCluster.last_seen_at.desc())
        )
        return [(int(r[0]), bytes(r[1]), int(r[2])) for r in self.db.execute(stmt).all()]

    # ------------------------------------------------------------------
    # Listing / counting (used by API + retention)
    # ------------------------------------------------------------------

    def count_by_status(self, status: UnknownClusterStatus) -> int:
        stmt = select(func.count(UnknownFaceCluster.id)).where(
            UnknownFaceCluster.status == status
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_by_status(
        self,
        status: UnknownClusterStatus,
        *,
        limit: int | None = None,
        order_desc: bool = True,
    ) -> Sequence[UnknownFaceCluster]:
        order_col = (
            UnknownFaceCluster.last_seen_at.desc()
            if order_desc
            else UnknownFaceCluster.last_seen_at.asc()
        )
        stmt = (
            select(UnknownFaceCluster)
            .where(UnknownFaceCluster.status == status)
            .order_by(order_col)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_oldest_ignored(self) -> UnknownFaceCluster | None:
        stmt = (
            select(UnknownFaceCluster)
            .where(UnknownFaceCluster.status == UnknownClusterStatus.IGNORED)
            .order_by(UnknownFaceCluster.last_seen_at.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def search(
        self,
        *,
        status: UnknownClusterStatus | None,
        label_query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[UnknownFaceCluster], int]:
        stmt = select(UnknownFaceCluster)
        count_stmt = select(func.count(UnknownFaceCluster.id))
        conds = []
        if status is not None:
            conds.append(UnknownFaceCluster.status == status)
        if label_query:
            like = f"%{label_query}%"
            conds.append(UnknownFaceCluster.label.ilike(like))
        if conds:
            stmt = stmt.where(and_(*conds))
            count_stmt = count_stmt.where(and_(*conds))
        stmt = (
            stmt.order_by(UnknownFaceCluster.last_seen_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.execute(stmt).scalars().all())
        total = int(self.db.execute(count_stmt).scalar_one())
        return items, total

    def representative_capture_ids(
        self, cluster_ids: list[int]
    ) -> dict[int, int]:
        """For each cluster id, return the id of its highest-quality KEEP
        capture (highest `det_score`, tie-break `sharpness_score`). Used
        to render a single thumbnail per cluster without loading the
        whole capture list.

        Implemented in two queries (max-quality per cluster, then capture
        ids that match) so it works on both Postgres and SQLite without
        needing window functions.
        """
        if not cluster_ids:
            return {}
        max_per_cluster = (
            select(
                UnknownFaceCapture.cluster_id,
                func.max(UnknownFaceCapture.det_score).label("max_score"),
            )
            .where(
                and_(
                    UnknownFaceCapture.cluster_id.in_(cluster_ids),
                    UnknownFaceCapture.status == UnknownCaptureStatus.KEEP,
                )
            )
            .group_by(UnknownFaceCapture.cluster_id)
            .subquery()
        )
        stmt = (
            select(
                UnknownFaceCapture.cluster_id,
                func.max(UnknownFaceCapture.id).label("capture_id"),
            )
            .join(
                max_per_cluster,
                and_(
                    UnknownFaceCapture.cluster_id == max_per_cluster.c.cluster_id,
                    UnknownFaceCapture.det_score == max_per_cluster.c.max_score,
                ),
            )
            .where(UnknownFaceCapture.status == UnknownCaptureStatus.KEEP)
            .group_by(UnknownFaceCapture.cluster_id)
        )
        return {int(r[0]): int(r[1]) for r in self.db.execute(stmt).all()}

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def list_for_purge(
        self,
        *,
        statuses: Iterable[UnknownClusterStatus],
        max_last_seen: datetime,
    ) -> list[UnknownFaceCluster]:
        """Clusters in the given statuses whose `last_seen_at` is older than
        the cutoff — eligible for hard deletion (files + rows) by the purge
        service.
        """
        statuses_list = list(statuses)
        if not statuses_list:
            return []
        stmt = (
            select(UnknownFaceCluster)
            .where(
                and_(
                    UnknownFaceCluster.status.in_(statuses_list),
                    UnknownFaceCluster.last_seen_at < max_last_seen,
                )
            )
            .order_by(UnknownFaceCluster.last_seen_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def update_after_capture(
        self,
        cluster: UnknownFaceCluster,
        *,
        new_centroid: bytes,
        new_centroid_dim: int,
        new_member_count: int,
        last_seen_at: datetime,
    ) -> None:
        cluster.centroid = new_centroid
        cluster.centroid_dim = new_centroid_dim
        cluster.member_count = new_member_count
        cluster.last_seen_at = last_seen_at
        self.db.flush()
