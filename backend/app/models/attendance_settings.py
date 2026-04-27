from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AttendanceSettings(Base):
    __tablename__ = "attendance_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_attendance_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Recognition
    face_match_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.45)
    face_min_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)

    # Camera pipeline
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    camera_fps: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Training
    train_min_images: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    train_max_images: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    auto_update_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_update_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.70)
    auto_update_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)

    # Office hours + thresholds (defaults: 09:30–18:30, no grace)
    work_start_time: Mapped[time | None] = mapped_column(
        Time, nullable=True, default=time(9, 30)
    )
    work_end_time: Mapped[time | None] = mapped_column(
        Time, nullable=True, default=time(18, 30)
    )
    grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    early_exit_grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Unknown-face capture pipeline (off by default — admin opt-in)
    unknown_capture_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    unknown_min_face_quality: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.65
    )
    unknown_min_face_size_px: Mapped[int] = mapped_column(
        Integer, nullable=False, default=80
    )
    unknown_min_sharpness: Mapped[float] = mapped_column(
        Float, nullable=False, default=50.0
    )
    unknown_capture_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    unknown_cluster_match_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.55
    )
    unknown_max_total_captures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5000
    )
    unknown_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )

    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
