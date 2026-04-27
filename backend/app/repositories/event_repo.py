from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select

from app.core.constants import EventType
from app.models.attendance_event import AttendanceEvent
from app.repositories.base_repo import BaseRepository


class EventRepository(BaseRepository[AttendanceEvent]):
    model = AttendanceEvent

    def list_for_employee_between(
        self, employee_id: int, start: datetime, end: datetime
    ) -> list[AttendanceEvent]:
        stmt = (
            select(AttendanceEvent)
            .where(
                and_(
                    AttendanceEvent.employee_id == employee_id,
                    AttendanceEvent.event_time >= start,
                    AttendanceEvent.event_time < end,
                )
            )
            .order_by(AttendanceEvent.event_time.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def latest_for_employee_between(
        self, employee_id: int, start: datetime, end: datetime
    ) -> AttendanceEvent | None:
        stmt = (
            select(AttendanceEvent)
            .where(
                and_(
                    AttendanceEvent.employee_id == employee_id,
                    AttendanceEvent.event_time >= start,
                    AttendanceEvent.event_time < end,
                )
            )
            .order_by(AttendanceEvent.event_time.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_filtered(
        self,
        *,
        employee_id: int | None,
        camera_id: int | None,
        event_type: EventType | None,
        start: datetime | None,
        end: datetime | None,
        is_manual: bool | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AttendanceEvent], int]:
        stmt = select(AttendanceEvent)
        count_stmt = select(func.count(AttendanceEvent.id))
        conds = []
        if employee_id is not None:
            conds.append(AttendanceEvent.employee_id == employee_id)
        if camera_id is not None:
            conds.append(AttendanceEvent.camera_id == camera_id)
        if event_type is not None:
            conds.append(AttendanceEvent.event_type == event_type)
        if start is not None:
            conds.append(AttendanceEvent.event_time >= start)
        if end is not None:
            conds.append(AttendanceEvent.event_time < end)
        if is_manual is not None:
            conds.append(AttendanceEvent.is_manual.is_(is_manual))
        if conds:
            stmt = stmt.where(and_(*conds))
            count_stmt = count_stmt.where(and_(*conds))
        stmt = stmt.order_by(AttendanceEvent.event_time.desc()).limit(limit).offset(offset)
        items = list(self.db.execute(stmt).scalars().all())
        total = int(self.db.execute(count_stmt).scalar_one())
        return items, total

    def count_since(self, since: datetime) -> int:
        stmt = select(func.count(AttendanceEvent.id)).where(
            AttendanceEvent.event_time >= since
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_by_hour(
        self, since: datetime, until: datetime
    ) -> list[tuple[datetime, int]]:
        """Hourly event counts in [since, until). Postgres date_trunc."""
        bucket = func.date_trunc("hour", AttendanceEvent.event_time).label("hour")
        stmt = (
            select(bucket, func.count(AttendanceEvent.id))
            .where(
                AttendanceEvent.event_time >= since,
                AttendanceEvent.event_time < until,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return [(row[0], int(row[1])) for row in self.db.execute(stmt).all()]

    def latest_type_per_employee_between(
        self, start: datetime, end: datetime
    ) -> dict[int, EventType]:
        """One row per employee: their latest event type within [start, end).

        Uses ROW_NUMBER() window function — O(N log N) with the
        (employee_id, event_time) index.
        """
        from sqlalchemy import Integer, cast
        from sqlalchemy.sql import literal_column

        rn = func.row_number().over(
            partition_by=AttendanceEvent.employee_id,
            order_by=AttendanceEvent.event_time.desc(),
        ).label("rn")
        sub = (
            select(
                AttendanceEvent.employee_id,
                AttendanceEvent.event_type,
                rn,
            )
            .where(
                AttendanceEvent.event_time >= start,
                AttendanceEvent.event_time < end,
            )
            .subquery()
        )
        stmt = select(sub.c.employee_id, sub.c.event_type).where(
            literal_column("rn") == cast(1, Integer)
        )
        return {int(row[0]): row[1] for row in self.db.execute(stmt).all()}

    def latest_event_per_employee_between(
        self, start: datetime, end: datetime
    ) -> list[AttendanceEvent]:
        """One AttendanceEvent per employee: their latest within [start, end),
        with the `camera` relationship eager-loaded. Ordered newest first.
        """
        from sqlalchemy import Integer, cast
        from sqlalchemy.orm import joinedload
        from sqlalchemy.sql import literal_column

        rn = func.row_number().over(
            partition_by=AttendanceEvent.employee_id,
            order_by=AttendanceEvent.event_time.desc(),
        ).label("rn")
        sub = (
            select(AttendanceEvent.id, rn)
            .where(
                AttendanceEvent.event_time >= start,
                AttendanceEvent.event_time < end,
            )
            .subquery()
        )
        ids_stmt = select(sub.c.id).where(
            literal_column("rn") == cast(1, Integer)
        )
        stmt = (
            select(AttendanceEvent)
            .where(AttendanceEvent.id.in_(ids_stmt))
            .options(joinedload(AttendanceEvent.camera))
            .order_by(AttendanceEvent.event_time.desc())
        )
        return list(self.db.execute(stmt).unique().scalars().all())

    def list_filtered_with_joins(
        self,
        *,
        employee_id: int | None,
        camera_id: int | None,
        event_type: EventType | None,
        start: datetime | None,
        end: datetime | None,
        is_manual: bool | None,
        has_snapshot: bool | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AttendanceEvent], int]:
        """Same filters as `list_filtered`, with employee + camera eager-loaded."""
        from sqlalchemy.orm import joinedload

        stmt = select(AttendanceEvent).options(
            joinedload(AttendanceEvent.employee),
            joinedload(AttendanceEvent.camera),
        )
        count_stmt = select(func.count(AttendanceEvent.id))
        conds = []
        if employee_id is not None:
            conds.append(AttendanceEvent.employee_id == employee_id)
        if camera_id is not None:
            conds.append(AttendanceEvent.camera_id == camera_id)
        if event_type is not None:
            conds.append(AttendanceEvent.event_type == event_type)
        if start is not None:
            conds.append(AttendanceEvent.event_time >= start)
        if end is not None:
            conds.append(AttendanceEvent.event_time < end)
        if is_manual is not None:
            conds.append(AttendanceEvent.is_manual.is_(is_manual))
        if has_snapshot is True:
            conds.append(AttendanceEvent.snapshot_path.is_not(None))
        elif has_snapshot is False:
            conds.append(AttendanceEvent.snapshot_path.is_(None))
        if conds:
            stmt = stmt.where(and_(*conds))
            count_stmt = count_stmt.where(and_(*conds))
        stmt = (
            stmt.order_by(AttendanceEvent.event_time.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.execute(stmt).unique().scalars().all())
        total = int(self.db.execute(count_stmt).scalar_one())
        return items, total

    def timeline(
        self, *, limit: int, offset: int
    ) -> list[AttendanceEvent]:
        from sqlalchemy.orm import joinedload

        stmt = (
            select(AttendanceEvent)
            .options(
                joinedload(AttendanceEvent.employee),
                joinedload(AttendanceEvent.camera),
            )
            .order_by(AttendanceEvent.event_time.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).unique().scalars().all())
