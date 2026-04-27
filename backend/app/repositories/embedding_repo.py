from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models.employee import Employee
from app.models.face_embedding import EmployeeFaceEmbedding
from app.models.face_image import EmployeeFaceImage
from app.repositories.base_repo import BaseRepository


class EmbeddingRepository(BaseRepository[EmployeeFaceEmbedding]):
    model = EmployeeFaceEmbedding

    def list_by_employee(self, employee_id: int) -> list[EmployeeFaceEmbedding]:
        stmt = (
            select(EmployeeFaceEmbedding)
            .where(EmployeeFaceEmbedding.employee_id == employee_id)
            .order_by(EmployeeFaceEmbedding.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_active_with_employee(
        self,
    ) -> list[tuple[EmployeeFaceEmbedding, Employee, EmployeeFaceImage]]:
        stmt = (
            select(EmployeeFaceEmbedding, Employee, EmployeeFaceImage)
            .join(Employee, Employee.id == EmployeeFaceEmbedding.employee_id)
            .join(EmployeeFaceImage, EmployeeFaceImage.id == EmployeeFaceEmbedding.image_id)
            .where(Employee.is_active.is_(True))
        )
        return [tuple(row) for row in self.db.execute(stmt).all()]  # type: ignore[misc]

    def delete_by_employee(self, employee_id: int) -> int:
        stmt = delete(EmployeeFaceEmbedding).where(
            EmployeeFaceEmbedding.employee_id == employee_id
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount or 0

    def delete_by_image(self, image_id: int) -> int:
        stmt = delete(EmployeeFaceEmbedding).where(EmployeeFaceEmbedding.image_id == image_id)
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount or 0

    def count_by_employee(self, employee_id: int) -> int:
        stmt = select(func.count(EmployeeFaceEmbedding.id)).where(
            EmployeeFaceEmbedding.employee_id == employee_id
        )
        return int(self.db.execute(stmt).scalar_one())
