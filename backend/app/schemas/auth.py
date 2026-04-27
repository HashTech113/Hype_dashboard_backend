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
