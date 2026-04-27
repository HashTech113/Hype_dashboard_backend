from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SessionStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


class DailyAttendance(Base):
    __tablename__ = "daily_attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_daily_attendance_employee_date"),
        Index("ix_daily_attendance_date_status", "work_date", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_out_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    out_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_work_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_break_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    break_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    early_exit_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.ABSENT,
    )
    is_manually_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_day_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    employee: Mapped["Employee"] = relationship(back_populates="daily_records")
