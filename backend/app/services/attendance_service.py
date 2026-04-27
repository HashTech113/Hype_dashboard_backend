from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from app.core.constants import (
    STATE_TRANSITIONS,
    TERMINAL_STATES,
    CameraType,
    EventType,
)
from app.core.exceptions import InvalidStateError, NotFoundError
from app.core.logger import get_logger
from app.models.admin import Admin
from app.models.attendance_event import AttendanceEvent
from app.repositories.camera_repo import CameraRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.event_repo import EventRepository
from app.services.daily_attendance_service import DailyAttendanceService
from app.services.snapshot_service import SnapshotService
from app.utils.time_utils import local_date_of, local_day_bounds, now_utc

log = get_logger(__name__)


@dataclass
class AutoEventOutcome:
    created: bool
    reason: str
    event: AttendanceEvent | None


class AttendanceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_repo = EventRepository(db)
        self.employee_repo = EmployeeRepository(db)
        self.camera_repo = CameraRepository(db)
        self.snapshot_service = SnapshotService()
        self.daily_service = DailyAttendanceService(db)

    def _current_state(self, employee_id: int, at_time: datetime) -> EventType | None:
        day_start, day_end = local_day_bounds(local_date_of(at_time))
        latest = self.event_repo.latest_for_employee_between(employee_id, day_start, day_end)
        return latest.event_type if latest is not None else None

    def process_auto_event(
        self,
        *,
        employee_id: int,
        camera_id: int,
        camera_type: CameraType,
        confidence: float,
        frame_bgr: np.ndarray,
        bbox: tuple[int, int, int, int],
        at_time: datetime | None = None,
    ) -> AutoEventOutcome:
        at = at_time or now_utc()
        employee = self.employee_repo.get(employee_id)
        if employee is None or not employee.is_active:
            return AutoEventOutcome(False, "employee_not_found_or_inactive", None)

        current = self._current_state(employee_id, at)
        if current in TERMINAL_STATES:
            return AutoEventOutcome(False, "day_closed", None)

        next_type = STATE_TRANSITIONS.get((current, camera_type))
        if next_type is None:
            return AutoEventOutcome(
                False, f"invalid_transition_from_{current}_via_{camera_type.value}", None
            )

        snapshot_path = self.snapshot_service.save_event_snapshot(
            employee_id=employee_id,
            event_type=next_type,
            frame_bgr=frame_bgr,
            bbox=bbox,
            captured_at=at,
        )

        event = AttendanceEvent(
            employee_id=employee_id,
            camera_id=camera_id,
            event_type=next_type,
            event_time=at,
            confidence=confidence,
            snapshot_path=snapshot_path,
            is_manual=False,
        )
        self.event_repo.add(event)
        self.daily_service.recompute(employee_id, local_date_of(at))
        log.info(
            "Auto event employee_id=%s code=%s type=%s camera_id=%s conf=%.3f",
            employee.id,
            employee.employee_code,
            next_type.value,
            camera_id,
            confidence,
        )
        return AutoEventOutcome(True, "ok", event)

    def create_manual_event(
        self,
        *,
        employee_id: int,
        event_type: EventType,
        event_time: datetime,
        camera_id: int | None,
        note: str | None,
        admin: Admin,
    ) -> AttendanceEvent:
        employee = self.employee_repo.get(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        if camera_id is not None and self.camera_repo.get(camera_id) is None:
            raise NotFoundError(f"Camera {camera_id} not found")

        event = AttendanceEvent(
            employee_id=employee_id,
            camera_id=camera_id,
            event_type=event_type,
            event_time=event_time,
            confidence=None,
            snapshot_path=None,
            is_manual=True,
            corrected_by=admin.id,
            note=note,
        )
        self.event_repo.add(event)
        self.daily_service.recompute(employee_id, local_date_of(event_time))
        log.info(
            "Manual event employee_id=%s type=%s by_admin=%s",
            employee_id,
            event_type.value,
            admin.username,
        )
        return event

    def update_event(
        self,
        *,
        event_id: int,
        event_type: EventType | None,
        event_time: datetime | None,
        camera_id: int | None,
        note: str | None,
        admin: Admin,
    ) -> AttendanceEvent:
        event = self.event_repo.get(event_id)
        if event is None:
            raise NotFoundError(f"Event {event_id} not found")

        original_employee = event.employee_id
        original_date = local_date_of(event.event_time)

        if camera_id is not None:
            if self.camera_repo.get(camera_id) is None:
                raise NotFoundError(f"Camera {camera_id} not found")
            event.camera_id = camera_id
        if event_type is not None:
            event.event_type = event_type
        if event_time is not None:
            event.event_time = event_time
        if note is not None:
            event.note = note

        event.is_manual = True
        event.corrected_by = admin.id
        self.db.flush()

        self.daily_service.recompute(original_employee, original_date)
        new_date = local_date_of(event.event_time)
        if new_date != original_date:
            self.daily_service.recompute(original_employee, new_date)
        log.info("Event id=%s updated by admin=%s", event_id, admin.username)
        return event

    def delete_event(self, event_id: int, admin: Admin) -> None:
        event = self.event_repo.get(event_id)
        if event is None:
            raise NotFoundError(f"Event {event_id} not found")
        employee_id = event.employee_id
        work_date = local_date_of(event.event_time)
        self.event_repo.delete(event)
        self.daily_service.recompute(employee_id, work_date)
        log.info("Event id=%s deleted by admin=%s", event_id, admin.username)

    @staticmethod
    def _assert_transition_legal(current: EventType | None, next_: EventType) -> None:
        order = [EventType.IN, EventType.BREAK_OUT, EventType.BREAK_IN, EventType.OUT]
        if current is None:
            if next_ != EventType.IN:
                raise InvalidStateError(f"First event of day must be IN, got {next_.value}")
            return
        if order.index(next_) != order.index(current) + 1:
            raise InvalidStateError(
                f"Illegal transition {current.value} -> {next_.value}"
            )
