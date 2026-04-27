from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.attendance_event import AttendanceEvent
    from app.models.daily_attendance import DailyAttendance
    from app.models.face_embedding import EmployeeFaceEmbedding
    from app.models.face_image import EmployeeFaceImage


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    face_images: Mapped[list["EmployeeFaceImage"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", lazy="selectin"
    )
    face_embeddings: Mapped[list["EmployeeFaceEmbedding"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list["AttendanceEvent"]] = relationship(back_populates="employee")
    daily_records: Mapped[list["DailyAttendance"]] = relationship(back_populates="employee")
