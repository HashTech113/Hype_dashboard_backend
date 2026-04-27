from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import time
from typing import Any

from app.core.logger import get_logger
from app.db.session import session_scope
from app.repositories.settings_repo import SettingsRepository

log = get_logger(__name__)


@dataclass(frozen=True)
class SettingsSnapshot:
    face_match_threshold: float
    face_min_quality: float
    cooldown_seconds: int
    camera_fps: int
    train_min_images: int
    train_max_images: int
    auto_update_enabled: bool
    auto_update_threshold: float
    auto_update_cooldown_seconds: int
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


class SettingsService:
    _instance: "SettingsService | None" = None
    _class_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: SettingsSnapshot | None = None

    @classmethod
    def instance(cls) -> "SettingsService":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def _to_snapshot(row) -> SettingsSnapshot:  # type: ignore[no-untyped-def]
        return SettingsSnapshot(
            face_match_threshold=float(row.face_match_threshold),
            face_min_quality=float(row.face_min_quality),
            cooldown_seconds=int(row.cooldown_seconds),
            camera_fps=int(row.camera_fps),
            train_min_images=int(row.train_min_images),
            train_max_images=int(row.train_max_images),
            auto_update_enabled=bool(row.auto_update_enabled),
            auto_update_threshold=float(row.auto_update_threshold),
            auto_update_cooldown_seconds=int(row.auto_update_cooldown_seconds),
            work_start_time=row.work_start_time,
            work_end_time=row.work_end_time,
            grace_minutes=int(row.grace_minutes),
            early_exit_grace_minutes=int(row.early_exit_grace_minutes),
            unknown_capture_enabled=bool(row.unknown_capture_enabled),
            unknown_min_face_quality=float(row.unknown_min_face_quality),
            unknown_min_face_size_px=int(row.unknown_min_face_size_px),
            unknown_min_sharpness=float(row.unknown_min_sharpness),
            unknown_capture_cooldown_seconds=int(row.unknown_capture_cooldown_seconds),
            unknown_cluster_match_threshold=float(row.unknown_cluster_match_threshold),
            unknown_max_total_captures=int(row.unknown_max_total_captures),
            unknown_retention_days=int(row.unknown_retention_days),
        )

    def load(self) -> SettingsSnapshot:
        with session_scope() as db:
            row = SettingsRepository(db).get()
            snap = self._to_snapshot(row)
        with self._lock:
            self._snapshot = snap
        log.info(
            "Settings loaded: threshold=%.3f cooldown=%ds fps=%d",
            snap.face_match_threshold,
            snap.cooldown_seconds,
            snap.camera_fps,
        )
        return snap

    def get(self) -> SettingsSnapshot:
        with self._lock:
            if self._snapshot is None:
                return self.load()
            return self._snapshot

    def update(self, data: dict[str, Any], admin_id: int | None) -> SettingsSnapshot:
        with session_scope() as db:
            row = SettingsRepository(db).get()
            for key, value in data.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            if admin_id is not None:
                row.updated_by = admin_id
            db.flush()
            snap = self._to_snapshot(row)
        with self._lock:
            self._snapshot = snap
        log.info("Settings updated by admin_id=%s", admin_id)
        return snap


def get_settings_service() -> SettingsService:
    return SettingsService.instance()
