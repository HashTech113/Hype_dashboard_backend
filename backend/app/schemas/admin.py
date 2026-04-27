from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_employees: int
    active_employees: int
    total_cameras: int
    active_cameras: int
    today_present: int
    today_incomplete: int
    today_absent: int
    events_last_24h: int


class LiveWorkerStatus(BaseModel):
    camera_id: int
    camera_name: str
    is_running: bool
    last_heartbeat: datetime | None
    last_heartbeat_age_seconds: float | None
    # `None` until the camera actually delivers a frame. Use this — NOT
    # `last_heartbeat_age_seconds` — to determine whether the camera is
    # really streaming.
    last_frame_age_seconds: float | None = None
    processed_frames: int
    events_generated: int
    auto_enrollments: int
    unknown_captures: int = 0
    unknown_skipped: int = 0
    last_error: str | None
