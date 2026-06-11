from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.session import get_sessionmaker
from app.models.admin import Admin
from app.services.auth_service import AuthService
from app.services.cooldown_service import CooldownService, get_cooldown_service
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.workers.camera_manager import CameraManager


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_face_service(request: Request) -> FaceService:
    svc: FaceService | None = getattr(request.app.state, "face_service", None)
    if svc is None:
        svc = FaceService()
        svc.load()
        request.app.state.face_service = svc
    return svc


def get_embedding_cache(request: Request) -> EmbeddingCache:
    cache: EmbeddingCache | None = getattr(request.app.state, "embedding_cache", None)
    if cache is None:
        cache = EmbeddingCache()
        cache.load_from_db()
        request.app.state.embedding_cache = cache
    return cache


def get_cooldown(_: Request = None) -> CooldownService:  # type: ignore[assignment]
    return get_cooldown_service()


def get_camera_manager(request: Request) -> CameraManager:
    mgr: CameraManager | None = getattr(request.app.state, "camera_manager", None)
    if mgr is None:
        raise RuntimeError("Camera manager not initialized")
    return mgr


def get_current_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Admin:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Empty token")
    admin = AuthService(db).resolve_admin(token)
    # Force-rotate gate: if the admin must change password (e.g. the
    # bootstrap super-admin on first login), block every endpoint except
    # the password-change endpoint itself and the /auth/me identity probe
    # the frontend uses to render the change-password screen.
    if admin.must_change_password:
        path = request.url.path or ""
        allowed_suffixes = ("/auth/change-password", "/auth/me")
        if not any(path.endswith(suffix) for suffix in allowed_suffixes):
            raise AuthorizationError(
                "Password change required before using the system",
                code="password_change_required",
            )
    return admin


def require_roles(*roles: Role):
    def _dep(admin: Admin = Depends(get_current_admin)) -> Admin:
        AuthService.require_role(admin, *roles)
        return admin

    return _dep
