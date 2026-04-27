from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.core.constants import EventType


class DashboardResponse(BaseModel):
    as_of: datetime
    work_date: date
    total_employees: int
    active_employees: int
    present_today: int
    absent_today: int
    incomplete_today: int
    inside_office: int
    on_break: int
    outside_office: int
    late_today: int
    early_exit_today: int
    events_last_24h: int
    total_cameras: int
    active_cameras: int


class HourBucketSchema(BaseModel):
    bucket_start: datetime
    count: int


class PresenceStatus(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    department: str | None
    status: str
    last_event_type: EventType | None
    last_event_time: datetime | None
    last_camera_name: str | None
    last_event_id: int | None


class TimelineItemSchema(BaseModel):
    event_id: int
    employee_id: int
    employee_code: str
    employee_name: str
    event_type: EventType
    event_time: datetime
    camera_id: int | None
    camera_name: str | None
    confidence: float | None
    is_manual: bool
    snapshot_available: bool
