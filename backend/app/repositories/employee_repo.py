from __future__ import annotations

from sqlalchemy import func, select

from app.models.employee import Employee
from app.repositories.base_repo import BaseRepository


class EmployeeRepository(BaseRepository[Employee]):
    model = Employee

    def get_by_code(self, employee_code: str) -> Employee | None:
        stmt = select(Employee).where(Employee.employee_code == employee_code)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_active(self) -> list[Employee]:
        stmt = select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.name)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_ids(self, ids: list[int]) -> dict[int, Employee]:
        if not ids:
            return {}
        stmt = select(Employee).where(Employee.id.in_(ids))
        return {e.id: e for e in self.db.execute(stmt).scalars().all()}

    def count(self, *, only_active: bool = False) -> int:
        stmt = select(func.count(Employee.id))
        if only_active:
            stmt = stmt.where(Employee.is_active.is_(True))
        return int(self.db.execute(stmt).scalar_one())

    def search(
        self,
        *,
        query: str | None,
        is_active: bool | None,
        department: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Employee], int]:
        stmt = select(Employee)
        count_stmt = select(func.count(Employee.id))
        if query:
            like = f"%{query}%"
            cond = (
                Employee.name.ilike(like)
                | Employee.employee_code.ilike(like)
                | Employee.email.ilike(like)
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        if is_active is not None:
            stmt = stmt.where(Employee.is_active.is_(is_active))
            count_stmt = count_stmt.where(Employee.is_active.is_(is_active))
        if department is not None:
            stmt = stmt.where(Employee.department == department)
            count_stmt = count_stmt.where(Employee.department == department)
        stmt = stmt.order_by(Employee.name).limit(limit).offset(offset)
        items = list(self.db.execute(stmt).scalars().all())
        total = int(self.db.execute(count_stmt).scalar_one())
        return items, total
