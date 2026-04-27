from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db, require_roles
from app.core.constants import Role
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.models.admin import Admin
from app.models.employee import Employee
from app.repositories.employee_repo import EmployeeRepository
from app.schemas.common import Page
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=Page[EmployeeRead])
def list_employees(
    q: str | None = None,
    is_active: bool | None = None,
    department: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Page[EmployeeRead]:
    items, total = EmployeeRepository(db).search(
        query=q,
        is_active=is_active,
        department=department,
        limit=limit,
        offset=offset,
    )
    return Page[EmployeeRead](
        items=[EmployeeRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/by-code/{employee_code}", response_model=EmployeeRead)
def get_employee_by_code(
    employee_code: str,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> EmployeeRead:
    emp = EmployeeRepository(db).get_by_code(employee_code)
    if emp is None:
        raise NotFoundError(f"Employee code '{employee_code}' not found")
    return EmployeeRead.model_validate(emp)


@router.get("/{employee_id}", response_model=EmployeeRead)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> EmployeeRead:
    emp = EmployeeRepository(db).get(employee_id)
    if emp is None:
        raise NotFoundError(f"Employee {employee_id} not found")
    return EmployeeRead.model_validate(emp)


@router.post("", response_model=EmployeeRead, status_code=201)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> EmployeeRead:
    repo = EmployeeRepository(db)
    if repo.get_by_code(payload.employee_code) is not None:
        raise AlreadyExistsError(f"employee_code '{payload.employee_code}' already exists")
    emp = Employee(
        employee_code=payload.employee_code,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        designation=payload.designation,
        department=payload.department,
        join_date=payload.join_date,
        is_active=payload.is_active,
    )
    repo.add(emp)
    return EmployeeRead.model_validate(emp)


@router.patch("/{employee_id}", response_model=EmployeeRead)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> EmployeeRead:
    repo = EmployeeRepository(db)
    emp = repo.get(employee_id)
    if emp is None:
        raise NotFoundError(f"Employee {employee_id} not found")
    data = payload.model_dump(exclude_unset=True)
    repo.update(emp, data)
    return EmployeeRead.model_validate(emp)


@router.delete("/{employee_id}", status_code=204, response_model=None)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> None:
    repo = EmployeeRepository(db)
    emp = repo.get(employee_id)
    if emp is None:
        raise NotFoundError(f"Employee {employee_id} not found")
    emp.is_active = False
