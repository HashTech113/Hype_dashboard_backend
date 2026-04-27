from __future__ import annotations

from sqlalchemy import func, select

from app.models.camera import Camera
from app.repositories.base_repo import BaseRepository


class CameraRepository(BaseRepository[Camera]):
    model = Camera

    def get_by_name(self, name: str) -> Camera | None:
        stmt = select(Camera).where(Camera.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_active(self) -> list[Camera]:
        stmt = select(Camera).where(Camera.is_active.is_(True)).order_by(Camera.name)
        return list(self.db.execute(stmt).scalars().all())

    def list_all(self) -> list[Camera]:
        stmt = select(Camera).order_by(Camera.name)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, *, only_active: bool = False) -> int:
        stmt = select(func.count(Camera.id))
        if only_active:
            stmt = stmt.where(Camera.is_active.is_(True))
        return int(self.db.execute(stmt).scalar_one())
