from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.constants import EventType, SessionStatus
from app.schemas.common import ORMModel


class AttendanceEventRead(ORMModel):
    id: int
    employee_id: int
    camera_id: int | None
    event_type: EventType
    event_time: datetime
    confidence: float | None
    snapshot_path: str | None
    is_manual: bool
    corrected_by: int | None
    note: str | None
    created_at: datetime


class AttendanceEventDetailRead(BaseModel):
    id: int
    employee_id: int
    employee_code: str
    employee_name: str
    camera_id: int | None
    camera_name: str | None
    event_type: EventType
    event_time: datetime
    confidence: float | None
    snapshot_available: bool
    is_manual: bool
    corrected_by: int | None
    note: str | None
    created_at: datetime


class ManualEventCreate(BaseModel):
    employee_id: int = Field(gt=0)
    event_type: EventType
    event_time: datetime
    camera_id: int | None = None
    note: str | None = Field(default=None, max_length=512)


class EventUpdate(BaseModel):
    event_type: EventType | None = None
    event_time: datetime | None = None
    camera_id: int | None = None
    note: str | None = None


class DailyAttendanceRead(ORMModel):
    id: int
    employee_id: int
    work_date: date
    in_time: datetime | None
    break_out_time: datetime | None
    break_in_time: datetime | None
    out_time: datetime | None
    total_work_seconds: int
    total_break_seconds: int
    break_count: int
    late_minutes: int
    early_exit_minutes: int
    status: SessionStatus
    is_manually_adjusted: bool
    is_day_closed: bool
    updated_at: datetime


class CloseDayResponse(BaseModel):
    work_date: date
    closed: int
    already_closed: int
    no_activity: int
