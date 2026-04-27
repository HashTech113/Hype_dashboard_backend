from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models.face_image import EmployeeFaceImage
from app.repositories.base_repo import BaseRepository


class FaceImageRepository(BaseRepository[EmployeeFaceImage]):
    model = EmployeeFaceImage

    def list_by_employee(self, employee_id: int) -> list[EmployeeFaceImage]:
        stmt = (
            select(EmployeeFaceImage)
            .where(EmployeeFaceImage.employee_id == employee_id)
            .order_by(EmployeeFaceImage.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_hash(self, employee_id: int, file_hash: str) -> EmployeeFaceImage | None:
        stmt = select(EmployeeFaceImage).where(
            EmployeeFaceImage.employee_id == employee_id,
            EmployeeFaceImage.file_hash == file_hash,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def delete_by_employee(self, employee_id: int) -> int:
        stmt = delete(EmployeeFaceImage).where(EmployeeFaceImage.employee_id == employee_id)
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount or 0

    def count_by_employee(self, employee_id: int) -> int:
        stmt = select(func.count(EmployeeFaceImage.id)).where(
            EmployeeFaceImage.employee_id == employee_id
        )
        return int(self.db.execute(stmt).scalar_one())
