from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_camera_manager, get_current_admin, get_db
from app.core.constants import SessionStatus
from app.models.admin import Admin
from app.repositories.camera_repo import CameraRepository
from app.repositories.daily_attendance_repo import DailyAttendanceRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.event_repo import EventRepository
from app.schemas.admin import LiveWorkerStatus, StatsResponse
from app.schemas.dashboard import (
    DashboardResponse,
    HourBucketSchema,
    PresenceStatus,
    TimelineItemSchema,
)
from app.services.dashboard_service import DashboardService
from app.utils.time_utils import now_local, now_utc
from app.workers.camera_manager import CameraManager

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=StatsResponse)
def stats(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> StatsResponse:
    employee_repo = EmployeeRepository(db)
    camera_repo = CameraRepository(db)
    daily_repo = DailyAttendanceRepository(db)
    event_repo = EventRepository(db)

    today = now_local().date()
    status_counts = daily_repo.count_by_status_for_date(today)
    since = now_utc() - timedelta(hours=24)

    return StatsResponse(
        total_employees=employee_repo.count(),
        active_employees=employee_repo.count(only_active=True),
        total_cameras=camera_repo.count(),
        active_cameras=camera_repo.count(only_active=True),
        today_present=status_counts.get(SessionStatus.PRESENT, 0),
        today_incomplete=status_counts.get(SessionStatus.INCOMPLETE, 0),
        today_absent=status_counts.get(SessionStatus.ABSENT, 0),
        events_last_24h=event_repo.count_since(since),
    )


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> DashboardResponse:
    snap = DashboardService(db).snapshot()
    return DashboardResponse(
        as_of=snap.as_of,
        work_date=snap.work_date,
        total_employees=snap.total_employees,
        active_employees=snap.active_employees,
        present_today=snap.present_today,
        absent_today=snap.absent_today,
        incomplete_today=snap.incomplete_today,
        inside_office=snap.inside_office,
        on_break=snap.on_break,
        outside_office=snap.outside_office,
        late_today=snap.late_today,
        early_exit_today=snap.early_exit_today,
        events_last_24h=snap.events_last_24h,
        total_cameras=snap.total_cameras,
        active_cameras=snap.active_cameras,
    )


@router.get("/dashboard/timeline", response_model=list[TimelineItemSchema])
def timeline(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[TimelineItemSchema]:
    items = DashboardService(db).timeline(limit=limit, offset=offset)
    return [
        TimelineItemSchema(
            event_id=i.event_id,
            employee_id=i.employee_id,
            employee_code=i.employee_code,
            employee_name=i.employee_name,
            event_type=i.event_type,
            event_time=i.event_time,
            camera_id=i.camera_id,
            camera_name=i.camera_name,
            confidence=i.confidence,
            is_manual=i.is_manual,
            snapshot_available=i.snapshot_available,
        )
        for i in items
    ]


@router.get("/presence", response_model=list[PresenceStatus])
def presence(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[PresenceStatus]:
    items = DashboardService(db).presence_list()
    return [
        PresenceStatus(
            employee_id=i.employee_id,
            employee_code=i.employee_code,
            employee_name=i.employee_name,
            department=i.department,
            status=i.status,
            last_event_type=i.last_event_type,
            last_event_time=i.last_event_time,
            last_camera_name=i.last_camera_name,
            last_event_id=i.last_event_id,
        )
        for i in items
    ]


@router.get("/dashboard/events-by-hour", response_model=list[HourBucketSchema])
def dashboard_events_by_hour(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[HourBucketSchema]:
    buckets = DashboardService(db).events_by_hour(hours=hours)
    return [
        HourBucketSchema(bucket_start=b.bucket_start, count=b.count) for b in buckets
    ]


@router.get("/live-status", response_model=list[LiveWorkerStatus])
def live_status(
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(get_current_admin),
) -> list[LiveWorkerStatus]:
    return [LiveWorkerStatus(**s) for s in manager.status()]
