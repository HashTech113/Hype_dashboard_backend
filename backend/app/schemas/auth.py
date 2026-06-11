from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import Role
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class AdminRead(ORMModel):
    id: int
    username: str
    full_name: str | None
    role: Role
    is_active: bool
    last_login_at: datetime | None
    password_changed_at: datetime | None = None


class AdminCreate(BaseModel):
    """SUPER_ADMIN only — create a new admin / VIEWER / ADMIN."""
    username: str = Field(min_length=3, max_length=64)
    full_name: str | None = Field(default=None, max_length=128)
    role: Role
    initial_password: str = Field(min_length=8, max_length=256)
    is_active: bool = True


class AdminUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None
    # SUPER_ADMIN can set a new password for an admin who forgot theirs.
    reset_password: str | None = Field(default=None, min_length=8, max_length=256)
