from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import UnknownCaptureStatus, UnknownClusterStatus
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.camera import Camera
    from app.models.employee import Employee


class UnknownFaceCluster(Base, TimestampMixin):
    """One row per uniquely-identified unknown person.

    A cluster's `centroid` is the L2-normalized mean of its KEEP captures'
    embeddings, stored as a contiguous float32 byte buffer for parity with
    `EmployeeFaceEmbedding.vector`. Online clustering matches a new face
    against every cluster centroid via cosine similarity; HDBSCAN-based
    re-clustering reconciles drift offline.
    """

    __tablename__ = "unknown_face_clusters"
    __table_args__ = (
        Index(
            "ix_unknown_face_clusters_status_last_seen",
            "status",
            "last_seen_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    centroid: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    centroid_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    model_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="buffalo_l"
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[UnknownClusterStatus] = mapped_column(
        SAEnum(UnknownClusterStatus, name="unknown_cluster_status"),
        nullable=False,
        default=UnknownClusterStatus.PENDING,
        index=True,
    )
    promoted_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    merged_into_cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "unknown_face_clusters.id",
            ondelete="SET NULL",
            # Explicit short name — the auto-generated
            # "fk_<table>_<col>_<referred_table>" exceeds Postgres'
            # 63-char identifier limit for this self-referential FK.
            name="fk_unknown_clusters_merged_into",
        ),
        nullable=True,
    )

    promoted_employee: Mapped["Employee | None"] = relationship(
        foreign_keys=[promoted_employee_id]
    )
    merged_into: Mapped["UnknownFaceCluster | None"] = relationship(
        remote_side="UnknownFaceCluster.id",
        foreign_keys=[merged_into_cluster_id],
    )
    captures: Mapped[list["UnknownFaceCapture"]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
        order_by="UnknownFaceCapture.captured_at.desc()",
    )


class UnknownFaceCapture(Base):
    """One row per face crop assigned to an unknown cluster.

    Stores the capture-time embedding verbatim (L2-normalized float32) so
    cluster centroids can be recomputed exactly and so promotion to an
    Employee can reuse the original buffalo_l vector — avoiding any
    drift from re-detecting on the smaller cropped JPG.
    """

    __tablename__ = "unknown_face_captures"
    __table_args__ = (
        Index(
            "ix_unknown_face_captures_cluster_time",
            "cluster_id",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("unknown_face_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    model_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="buffalo_l"
    )
    camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    bbox_x: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_w: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_h: Mapped[int] = mapped_column(Integer, nullable=False)
    det_score: Mapped[float] = mapped_column(Float, nullable=False)
    sharpness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[UnknownCaptureStatus] = mapped_column(
        SAEnum(UnknownCaptureStatus, name="unknown_capture_status"),
        nullable=False,
        default=UnknownCaptureStatus.KEEP,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cluster: Mapped["UnknownFaceCluster"] = relationship(back_populates="captures")
    camera: Mapped["Camera | None"] = relationship()
