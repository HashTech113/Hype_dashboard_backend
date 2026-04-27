from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attendance_settings import AttendanceSettings


class SettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> AttendanceSettings:
        stmt = select(AttendanceSettings).where(AttendanceSettings.id == 1)
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            row = AttendanceSettings(id=1)
            self.db.add(row)
            self.db.flush()
        return row
