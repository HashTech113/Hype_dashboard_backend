from __future__ import annotations

from fastapi import APIRouter, Depends, Request
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


def _client_ip(request: Request) -> str | None:
    # Honor X-Forwarded-For if Caddy / Nginx is in front. Used for the
    # PASSWORD_CHANGED audit row only — login events are not audited.
    fwd = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    _, token = AuthService(db).authenticate(
        payload.username,
        payload.password,
        source_ip=_client_ip(request),
    )
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
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> None:
    AuthService(db).change_password(
        admin,
        payload.current_password,
        payload.new_password,
        source_ip=_client_ip(request),
    )
