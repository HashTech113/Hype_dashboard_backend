"""Authentication & authorization.

Simple credential check + bcrypt + JWT. No brute-force lockout, no
force-rotate gate, no login audit log (removed at operator request — the
deployment is a single-PC on-prem office system on a private LAN where
those features were more annoying than helpful).

Kept:
  - bcrypt password hashing
  - JWT signing + verification
  - RBAC (require_role)
  - Voluntary password change endpoint (/auth/change-password)
  - The audit_log table itself (still used by erasure + admin mgmt)
"""
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
from app.models.compliance import AdminAuditLog
from app.repositories.admin_repo import AdminRepository
from app.utils.time_utils import now_utc

log = get_logger(__name__)


def _record_audit(
    db: Session,
    *,
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    source_ip: str | None = None,
    detail: str | None = None,
) -> None:
    """Append one row to admin_audit_log.

    NEVER raises — audit failure must not break the user-facing flow.
    Used by sensitive non-login actions (admin create/update, erasure,
    password change). Login events are NOT audited.
    """
    try:
        row = AdminAuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            source_ip=source_ip,
            detail=detail,
            created_at=now_utc(),
        )
        db.add(row)
        db.flush()
    except Exception:
        log.exception("audit-log write failed for action=%s", action)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.admin_repo = AdminRepository(db)

    def authenticate(
        self, username: str, password: str, *, source_ip: str | None = None
    ) -> tuple[Admin, str]:
        # source_ip is accepted (the router passes it) but unused — kept
        # in the signature so the router doesn't need to change.
        _ = source_ip
        admin = self.admin_repo.get_by_username(username)
        if admin is None or not admin.is_active:
            raise AuthenticationError("Invalid credentials")
        if not verify_password(password, admin.password_hash):
            raise AuthenticationError("Invalid credentials")
        admin.last_login_at = now_utc()
        self.db.flush()
        token = create_access_token(
            subject=admin.id, extra={"role": admin.role.value}
        )
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
            raise AuthorizationError(
                f"Requires one of: {', '.join(r.value for r in allowed)}"
            )

    def change_password(
        self,
        admin: Admin,
        current_password: str,
        new_password: str,
        *,
        source_ip: str | None = None,
    ) -> None:
        if not verify_password(current_password, admin.password_hash):
            raise AuthenticationError("Current password is incorrect")
        if current_password == new_password:
            raise AuthenticationError("New password must differ from current password")
        if len(new_password) < 8:
            raise AuthenticationError("New password must be at least 8 characters")
        admin.password_hash = hash_password(new_password)
        admin.password_changed_at = now_utc()
        admin.must_change_password = False
        self.db.flush()
        log.info("Password changed for admin id=%s username=%s", admin.id, admin.username)
        _record_audit(
            self.db,
            admin_id=admin.id,
            action="PASSWORD_CHANGED",
            target_type="Admin",
            target_id=admin.id,
            source_ip=source_ip,
        )


def bootstrap_admin() -> None:
    """Seed the initial SUPER_ADMIN if no admin exists."""
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
            must_change_password=True,
        )
        db.add(admin)
        log.warning(
            "Bootstrapped initial super-admin '%s' — password change REQUIRED on first login",
            settings.BOOTSTRAP_ADMIN_USERNAME,
        )
