from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import Role
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logger import get_logger
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import session_scope
from app.models.admin import Admin
from app.repositories.admin_repo import AdminRepository
from app.utils.time_utils import now_utc

log = get_logger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.admin_repo = AdminRepository(db)

    def authenticate(self, username: str, password: str) -> tuple[Admin, str]:
        admin = self.admin_repo.get_by_username(username)
        if admin is None or not admin.is_active:
            raise AuthenticationError("Invalid credentials")
        if not verify_password(password, admin.password_hash):
            raise AuthenticationError("Invalid credentials")
        admin.last_login_at = now_utc()
        self.db.flush()
        token = create_access_token(subject=admin.id, extra={"role": admin.role.value})
        return admin, token

    def resolve_admin(self, token: str) -> Admin:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        sub = payload.get("sub")
        if sub is None:
            raise AuthenticationError("Invalid token")
        try:
            admin_id = int(sub)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("Invalid token subject") from exc
        admin = self.admin_repo.get(admin_id)
        if admin is None or not admin.is_active:
            raise AuthenticationError("Admin not found or inactive")
        return admin

    @staticmethod
    def require_role(admin: Admin, *allowed: Role) -> None:
        if admin.role not in allowed:
            raise AuthorizationError(f"Requires one of: {', '.join(r.value for r in allowed)}")

    def change_password(self, admin: Admin, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, admin.password_hash):
            raise AuthenticationError("Current password is incorrect")
        if current_password == new_password:
            raise AuthenticationError("New password must differ from current password")
        admin.password_hash = hash_password(new_password)
        self.db.flush()
        log.info("Password changed for admin id=%s username=%s", admin.id, admin.username)


def bootstrap_admin() -> None:
    settings = get_settings()
    with session_scope() as db:
        repo = AdminRepository(db)
        if repo.count() > 0:
            return
        admin = Admin(
            username=settings.BOOTSTRAP_ADMIN_USERNAME,
            password_hash=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
            role=Role.SUPER_ADMIN,
            is_active=True,
        )
        db.add(admin)
        log.warning(
            "Bootstrapped initial super-admin '%s' — change the password immediately",
            settings.BOOTSTRAP_ADMIN_USERNAME,
        )
