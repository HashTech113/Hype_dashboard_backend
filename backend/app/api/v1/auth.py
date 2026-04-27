from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.config import get_settings
from app.models.admin import Admin
from app.schemas.auth import (
    AdminRead,
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _, token = AuthService(db).authenticate(payload.username, payload.password)
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=AdminRead)
def me(admin: Admin = Depends(get_current_admin)) -> AdminRead:
    return AdminRead.model_validate(admin)


@router.post("/change-password", status_code=204, response_model=None)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> None:
    AuthService(db).change_password(admin, payload.current_password, payload.new_password)
