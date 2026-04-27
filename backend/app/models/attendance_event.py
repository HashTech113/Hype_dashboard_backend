from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EventType
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.admin import Admin
    from app.models.camera import Camera
    from app.models.employee import Employee


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        Index("ix_attendance_events_employee_time", "employee_id", "event_time"),
        Index("ix_attendance_events_event_time", "event_time"),
        Index("ix_attendance_events_employee_type_time", "employee_id", "event_type", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type"), nullable=False
    )
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    corrected_by: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee: Mapped["Employee"] = relationship(back_populates="events")
    camera: Mapped["Camera | None"] = relationship()
    admin: Mapped["Admin | None"] = relationship()
