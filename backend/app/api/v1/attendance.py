from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db, require_roles
from app.core.constants import EventType, Role
from app.models.admin import Admin
from app.repositories.daily_attendance_repo import DailyAttendanceRepository
from app.repositories.event_repo import EventRepository
from app.schemas.attendance import (
    AttendanceEventDetailRead,
    AttendanceEventRead,
    CloseDayResponse,
    DailyAttendanceRead,
    EventUpdate,
    ManualEventCreate,
)
from app.schemas.common import Page
from app.services.attendance_service import AttendanceService
from app.services.daily_attendance_service import DailyAttendanceService
from app.utils.time_utils import local_day_bounds, now_local

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("/events", response_model=Page[AttendanceEventRead])
def list_events(
    employee_id: int | None = None,
    camera_id: int | None = None,
    event_type: EventType | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    is_manual: bool | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Page[AttendanceEventRead]:
    items, total = EventRepository(db).list_filtered(
        employee_id=employee_id,
        camera_id=camera_id,
        event_type=event_type,
        start=start,
        end=end,
        is_manual=is_manual,
        limit=limit,
        offset=offset,
    )
    return Page[AttendanceEventRead](
        items=[AttendanceEventRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events/detailed", response_model=Page[AttendanceEventDetailRead])
def list_events_detailed(
    employee_id: int | None = None,
    camera_id: int | None = None,
    event_type: EventType | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    is_manual: bool | None = None,
    has_snapshot: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Page[AttendanceEventDetailRead]:
    items, total = EventRepository(db).list_filtered_with_joins(
        employee_id=employee_id,
        camera_id=camera_id,
        event_type=event_type,
        start=start,
        end=end,
        is_manual=is_manual,
        has_snapshot=has_snapshot,
        limit=limit,
        offset=offset,
    )
    return Page[AttendanceEventDetailRead](
        items=[
            AttendanceEventDetailRead(
                id=e.id,
                employee_id=e.employee_id,
                employee_code=e.employee.employee_code if e.employee else "",
                employee_name=e.employee.name if e.employee else "",
                camera_id=e.camera_id,
                camera_name=e.camera.name if e.camera else None,
                event_type=e.event_type,
                event_time=e.event_time,
                confidence=e.confidence,
                snapshot_available=bool(e.snapshot_path),
                is_manual=e.is_manual,
                corrected_by=e.corrected_by,
                note=e.note,
                created_at=e.created_at,
            )
            for e in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/events", response_model=AttendanceEventRead, status_code=201)
def create_manual_event(
    payload: ManualEventCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> AttendanceEventRead:
    event = AttendanceService(db).create_manual_event(
        employee_id=payload.employee_id,
        event_type=payload.event_type,
        event_time=payload.event_time,
        camera_id=payload.camera_id,
        note=payload.note,
        admin=admin,
    )
    return AttendanceEventRead.model_validate(event)


@router.patch("/events/{event_id}", response_model=AttendanceEventRead)
def update_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> AttendanceEventRead:
    event = AttendanceService(db).update_event(
        event_id=event_id,
        event_type=payload.event_type,
        event_time=payload.event_time,
        camera_id=payload.camera_id,
        note=payload.note,
        admin=admin,
    )
    return AttendanceEventRead.model_validate(event)


@router.delete("/events/{event_id}", status_code=204, response_model=None)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> None:
    AttendanceService(db).delete_event(event_id, admin)


@router.get("/daily", response_model=list[DailyAttendanceRead])
def list_daily(
    work_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[DailyAttendanceRead]:
    items = DailyAttendanceRepository(db).list_by_date(work_date)
    return [DailyAttendanceRead.model_validate(i) for i in items]


@router.get("/daily/employee/{employee_id}", response_model=list[DailyAttendanceRead])
def list_daily_for_employee(
    employee_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[DailyAttendanceRead]:
    items = DailyAttendanceRepository(db).list_for_employee_range(
        employee_id, start_date, end_date
    )
    return [DailyAttendanceRead.model_validate(i) for i in items]


@router.post("/recompute")
def recompute(
    work_date: date,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> dict[str, int | str]:
    """Force-recompute the daily rollup for `work_date`.

    If `employee_id` is omitted, recomputes every employee who had events that
    day. Use after data imports, bulk corrections, or to heal any suspected
    drift between attendance_events and daily_attendance.
    """
    touched = DailyAttendanceService(db).recompute_range(
        employee_id=employee_id, start=work_date, end=work_date
    )
    return {"work_date": work_date.isoformat(), "touched": touched}


@router.post("/recompute-range")
def recompute_range(
    start_date: date,
    end_date: date,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> dict[str, int | str]:
    touched = DailyAttendanceService(db).recompute_range(
        employee_id=employee_id, start=start_date, end=end_date
    )
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "touched": touched,
    }


@router.post("/close-day", response_model=CloseDayResponse)
def close_day(
    work_date: date,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> CloseDayResponse:
    result = DailyAttendanceService(db).close_day(work_date, admin)
    return CloseDayResponse(
        work_date=work_date,
        closed=result.closed,
        already_closed=result.already_closed,
        no_activity=result.no_activity,
    )


@router.post("/reopen-day", status_code=200)
def reopen_day(
    work_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> dict[str, int]:
    count = DailyAttendanceService(db).reopen_day(work_date)
    return {"reopened": count}


@router.get("/events/today", response_model=list[AttendanceEventRead])
def events_today(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[AttendanceEventRead]:
    start, end = local_day_bounds(now_local().date())
    items = EventRepository(db).list_for_employee_between(employee_id, start, end)
    return [AttendanceEventRead.model_validate(i) for i in items]
