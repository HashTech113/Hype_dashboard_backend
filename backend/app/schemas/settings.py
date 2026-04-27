from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SettingsRead(ORMModel):
    id: int
    # Recognition
    face_match_threshold: float
    face_min_quality: float
    # Camera pipeline
    cooldown_seconds: int
    camera_fps: int
    # Training
    train_min_images: int
    train_max_images: int
    auto_update_enabled: bool
    auto_update_threshold: float
    auto_update_cooldown_seconds: int
    # Office hours + thresholds
    work_start_time: time | None
    work_end_time: time | None
    grace_minutes: int
    early_exit_grace_minutes: int
    # Unknown-face capture pipeline
    unknown_capture_enabled: bool
    unknown_min_face_quality: float
    unknown_min_face_size_px: int
    unknown_min_sharpness: float
    unknown_capture_cooldown_seconds: int
    unknown_cluster_match_threshold: float
    unknown_max_total_captures: int
    unknown_retention_days: int
    # Meta
    updated_by: int | None
    updated_at: datetime


class SettingsUpdate(BaseModel):
    # Recognition
    face_match_threshold: float | None = Field(default=None, gt=0.0, lt=1.0)
    face_min_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    # Camera pipeline
    cooldown_seconds: int | None = Field(default=None, ge=0, le=300)
    camera_fps: int | None = Field(default=None, ge=1, le=30)
    # Training
    train_min_images: int | None = Field(default=None, ge=1, le=100)
    train_max_images: int | None = Field(default=None, ge=1, le=100)
    auto_update_enabled: bool | None = None
    auto_update_threshold: float | None = Field(default=None, gt=0.0, lt=1.0)
    auto_update_cooldown_seconds: int | None = Field(default=None, ge=60, le=86400)
    # Office hours + thresholds
    work_start_time: time | None = None
    work_end_time: time | None = None
    grace_minutes: int | None = Field(default=None, ge=0, le=120)
    early_exit_grace_minutes: int | None = Field(default=None, ge=0, le=120)
    # Unknown-face capture pipeline
    unknown_capture_enabled: bool | None = None
    unknown_min_face_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    unknown_min_face_size_px: int | None = Field(default=None, ge=16, le=4096)
    unknown_min_sharpness: float | None = Field(default=None, ge=0.0, le=10000.0)
    unknown_capture_cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    unknown_cluster_match_threshold: float | None = Field(default=None, gt=0.0, lt=1.0)
    unknown_max_total_captures: int | None = Field(default=None, ge=100, le=1_000_000)
    unknown_retention_days: int | None = Field(default=None, ge=1, le=3650)
