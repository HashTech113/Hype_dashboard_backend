from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class EmployeeBase(BaseModel):
    employee_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    designation: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=128)
    join_date: date | None = None


class EmployeeCreate(EmployeeBase):
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    designation: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=128)
    join_date: date | None = None
    is_active: bool | None = None


class EmployeeRead(ORMModel):
    id: int
    employee_code: str
    name: str
    email: str | None
    phone: str | None
    designation: str | None
    department: str | None
    join_date: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
