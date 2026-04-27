from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db, require_roles
from app.core.constants import Role
from app.core.exceptions import NotFoundError
from app.models.admin import Admin
from app.models.attendance_event import AttendanceEvent
from app.repositories.event_repo import EventRepository
from app.schemas.attendance import AttendanceEventRead
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


class StorageStatsResponse(BaseModel):
    root: str
    total_files: int
    total_bytes: int
    total_mb: float
    oldest_date: str | None
    newest_date: str | None


class PurgeResponse(BaseModel):
    before_date: date
    removed_files: int
    removed_bytes: int
    removed_mb: float
    removed_dirs: int
    db_rows_cleared: int


@router.get("/stats", response_model=StorageStatsResponse)
def storage_stats(
    _: Admin = Depends(get_current_admin),
) -> StorageStatsResponse:
    stats = SnapshotService().storage_stats()
    return StorageStatsResponse(
        root=stats.root,
        total_files=stats.total_files,
        total_bytes=stats.total_bytes,
        total_mb=round(stats.total_bytes / (1024 * 1024), 2),
        oldest_date=stats.oldest_date,
        newest_date=stats.newest_date,
    )


@router.delete("/purge", response_model=PurgeResponse)
def purge_snapshots(
    before_date: date,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> PurgeResponse:
    result = SnapshotService().purge_before(before_date)
    cutoff_dt = datetime.combine(before_date, datetime.min.time())
    stmt = (
        update(AttendanceEvent)
        .where(
            AttendanceEvent.snapshot_path.is_not(None),
            AttendanceEvent.event_time < cutoff_dt,
        )
        .values(snapshot_path=None)
    )
    res = db.execute(stmt)
    db_rows = int(res.rowcount or 0)
    return PurgeResponse(
        before_date=before_date,
        removed_files=result.removed_files,
        removed_bytes=result.removed_bytes,
        removed_mb=round(result.removed_bytes / (1024 * 1024), 2),
        removed_dirs=result.removed_dirs,
        db_rows_cleared=db_rows,
    )


@router.get("/by-event/{event_id}")
def get_event_snapshot(
    event_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> FileResponse:
    event = EventRepository(db).get(event_id)
    if event is None:
        raise NotFoundError(f"Event {event_id} not found")
    if not event.snapshot_path:
        raise NotFoundError(f"Event {event_id} has no snapshot")
    path = Path(event.snapshot_path)
    if not path.exists():
        raise NotFoundError(f"Snapshot file missing: {event.snapshot_path}")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


@router.get("", response_model=list[AttendanceEventRead])
def list_events_with_snapshots(
    employee_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[AttendanceEventRead]:
    items, _total = EventRepository(db).list_filtered(
        employee_id=employee_id,
        camera_id=None,
        event_type=None,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    return [AttendanceEventRead.model_validate(i) for i in items if i.snapshot_path]
