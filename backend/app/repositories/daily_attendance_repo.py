from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select

from app.core.constants import SessionStatus
from app.models.daily_attendance import DailyAttendance
from app.repositories.base_repo import BaseRepository


class DailyAttendanceRepository(BaseRepository[DailyAttendance]):
    model = DailyAttendance

    def get_for_day(self, employee_id: int, work_date: date) -> DailyAttendance | None:
        stmt = select(DailyAttendance).where(
            and_(
                DailyAttendance.employee_id == employee_id,
                DailyAttendance.work_date == work_date,
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert_for_day(self, employee_id: int, work_date: date) -> DailyAttendance:
        existing = self.get_for_day(employee_id, work_date)
        if existing is not None:
            return existing
        row = DailyAttendance(
            employee_id=employee_id,
            work_date=work_date,
            status=SessionStatus.ABSENT,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_by_date(self, work_date: date) -> list[DailyAttendance]:
        stmt = select(DailyAttendance).where(DailyAttendance.work_date == work_date)
        return list(self.db.execute(stmt).scalars().all())

    def list_for_employee_range(
        self, employee_id: int, start: date, end: date
    ) -> list[DailyAttendance]:
        stmt = (
            select(DailyAttendance)
            .where(
                and_(
                    DailyAttendance.employee_id == employee_id,
                    DailyAttendance.work_date >= start,
                    DailyAttendance.work_date <= end,
                )
            )
            .order_by(DailyAttendance.work_date.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_in_range(self, start: date, end: date) -> list[DailyAttendance]:
        stmt = (
            select(DailyAttendance)
            .where(
                and_(
                    DailyAttendance.work_date >= start,
                    DailyAttendance.work_date <= end,
                )
            )
            .order_by(DailyAttendance.work_date.asc(), DailyAttendance.employee_id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_by_status_for_date(self, work_date: date) -> dict[SessionStatus, int]:
        stmt = (
            select(DailyAttendance.status, func.count(DailyAttendance.id))
            .where(DailyAttendance.work_date == work_date)
            .group_by(DailyAttendance.status)
        )
        rows = self.db.execute(stmt).all()
        return {row[0]: int(row[1]) for row in rows}

    def count_late_for_date(self, work_date: date) -> int:
        stmt = select(func.count(DailyAttendance.id)).where(
            and_(
                DailyAttendance.work_date == work_date,
                DailyAttendance.late_minutes > 0,
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_early_exit_for_date(self, work_date: date) -> int:
        stmt = select(func.count(DailyAttendance.id)).where(
            and_(
                DailyAttendance.work_date == work_date,
                DailyAttendance.early_exit_minutes > 0,
            )
        )
        return int(self.db.execute(stmt).scalar_one())
