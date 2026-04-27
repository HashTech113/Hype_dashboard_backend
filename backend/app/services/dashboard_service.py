from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.constants import EventType, SessionStatus
from app.models.attendance_event import AttendanceEvent
from app.repositories.camera_repo import CameraRepository
from app.repositories.daily_attendance_repo import DailyAttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.event_repo import EventRepository
from app.utils.time_utils import local_day_bounds, now_local, now_utc


@dataclass
class DashboardSnapshot:
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


@dataclass
class HourBucket:
    bucket_start: datetime
    count: int


@dataclass
class PresenceItem:
    employee_id: int
    employee_code: str
    employee_name: str
    department: str | None
    status: str  # "INSIDE" | "ON_BREAK" | "OUTSIDE" | "ABSENT"
    last_event_type: EventType | None
    last_event_time: datetime | None
    last_camera_name: str | None
    last_event_id: int | None


@dataclass
class TimelineItem:
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


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_repo = EventRepository(db)
        self.daily_repo = DailyAttendanceRepository(db)
        self.employee_repo = EmployeeRepository(db)
        self.camera_repo = CameraRepository(db)

    def snapshot(self) -> DashboardSnapshot:
        today = now_local().date()
        day_start, day_end = local_day_bounds(today)

        total_employees = self.employee_repo.count()
        active_employees = self.employee_repo.count(only_active=True)

        status_counts = self.daily_repo.count_by_status_for_date(today)
        present = status_counts.get(SessionStatus.PRESENT, 0)
        incomplete = status_counts.get(SessionStatus.INCOMPLETE, 0)
        # Absent = active employees who have no daily row with PRESENT/INCOMPLETE today.
        absent = max(0, active_employees - present - incomplete)

        latest = self.event_repo.latest_type_per_employee_between(day_start, day_end)
        inside = 0
        on_break = 0
        outside = 0
        for ev_type in latest.values():
            if ev_type in (EventType.IN, EventType.BREAK_IN):
                inside += 1
            elif ev_type == EventType.BREAK_OUT:
                on_break += 1
            elif ev_type == EventType.OUT:
                outside += 1

        late_today = self.daily_repo.count_late_for_date(today)
        early_exit_today = self.daily_repo.count_early_exit_for_date(today)
        events_last_24h = self.event_repo.count_since(now_utc() - timedelta(hours=24))

        total_cameras = self.camera_repo.count()
        active_cameras = self.camera_repo.count(only_active=True)

        return DashboardSnapshot(
            as_of=now_utc(),
            work_date=today,
            total_employees=total_employees,
            active_employees=active_employees,
            present_today=present + incomplete,  # anyone who has shown up counts as present
            absent_today=absent,
            incomplete_today=incomplete,
            inside_office=inside,
            on_break=on_break,
            outside_office=outside,
            late_today=late_today,
            early_exit_today=early_exit_today,
            events_last_24h=events_last_24h,
            total_cameras=total_cameras,
            active_cameras=active_cameras,
        )

    def presence_list(self) -> list[PresenceItem]:
        """Return every active employee with their current presence state today.

        Status derivation from last event:
          IN | BREAK_IN  → INSIDE
          BREAK_OUT      → ON_BREAK
          OUT            → OUTSIDE
          no event       → ABSENT
        """
        today = now_local().date()
        day_start, day_end = local_day_bounds(today)

        latest_events = self.event_repo.latest_event_per_employee_between(
            day_start, day_end
        )
        by_emp: dict[int, PresenceItem] = {}
        for ev in latest_events:
            status = self._status_for(ev.event_type)
            by_emp[ev.employee_id] = PresenceItem(
                employee_id=ev.employee_id,
                employee_code="",  # filled below
                employee_name="",
                department=None,
                status=status,
                last_event_type=ev.event_type,
                last_event_time=ev.event_time,
                last_camera_name=ev.camera.name if ev.camera else None,
                last_event_id=ev.id,
            )

        employees = self.employee_repo.list_active()
        out: list[PresenceItem] = []
        for emp in employees:
            item = by_emp.get(emp.id)
            if item is None:
                out.append(
                    PresenceItem(
                        employee_id=emp.id,
                        employee_code=emp.employee_code,
                        employee_name=emp.name,
                        department=emp.department,
                        status="ABSENT",
                        last_event_type=None,
                        last_event_time=None,
                        last_camera_name=None,
                        last_event_id=None,
                    )
                )
            else:
                item.employee_code = emp.employee_code
                item.employee_name = emp.name
                item.department = emp.department
                out.append(item)

        status_rank = {"INSIDE": 0, "ON_BREAK": 1, "OUTSIDE": 2, "ABSENT": 3}
        out.sort(
            key=lambda i: (
                status_rank.get(i.status, 99),
                -(i.last_event_time.timestamp() if i.last_event_time else 0),
                i.employee_name,
            )
        )
        return out

    @staticmethod
    def _status_for(event_type: EventType) -> str:
        if event_type in (EventType.IN, EventType.BREAK_IN):
            return "INSIDE"
        if event_type == EventType.BREAK_OUT:
            return "ON_BREAK"
        if event_type == EventType.OUT:
            return "OUTSIDE"
        return "ABSENT"

    def events_by_hour(self, hours: int = 24) -> list[HourBucket]:
        """Hourly event counts for the last `hours` hours, zero-filled.

        Returns exactly `hours` buckets, oldest → newest, each aligned to the
        top of the hour (UTC).
        """
        hours = max(1, min(hours, 168))
        now_ts = now_utc().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        since = now_ts - timedelta(hours=hours)

        raw = self.event_repo.count_by_hour(since, now_ts)
        by_hour: dict[datetime, int] = {}
        for ts, c in raw:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=now_ts.tzinfo)
            by_hour[ts.replace(minute=0, second=0, microsecond=0)] = c

        buckets: list[HourBucket] = []
        cursor = since
        while cursor < now_ts:
            buckets.append(HourBucket(bucket_start=cursor, count=by_hour.get(cursor, 0)))
            cursor += timedelta(hours=1)
        return buckets

    def timeline(self, *, limit: int, offset: int) -> list[TimelineItem]:
        events = self.event_repo.timeline(limit=limit, offset=offset)
        return [self._to_item(ev) for ev in events]

    def timeline_filtered(
        self,
        *,
        employee_id: int | None,
        event_types: Iterable[EventType] | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> list[TimelineItem]:
        # Reuse list_filtered but re-fetch with joined loads for display.
        items, _total = self.event_repo.list_filtered(
            employee_id=employee_id,
            camera_id=None,
            event_type=next(iter(event_types)) if event_types else None,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        ids = [i.id for i in items]
        if not ids:
            return []
        full = self.event_repo.timeline(limit=len(ids), offset=0)
        wanted = {i for i in ids}
        return [self._to_item(ev) for ev in full if ev.id in wanted]

    @staticmethod
    def _to_item(ev: AttendanceEvent) -> TimelineItem:
        return TimelineItem(
            event_id=ev.id,
            employee_id=ev.employee_id,
            employee_code=ev.employee.employee_code if ev.employee else "",
            employee_name=ev.employee.name if ev.employee else "",
            event_type=ev.event_type,
            event_time=ev.event_time,
            camera_id=ev.camera_id,
            camera_name=ev.camera.name if ev.camera else None,
            confidence=ev.confidence,
            is_manual=ev.is_manual,
            snapshot_available=bool(ev.snapshot_path),
        )
