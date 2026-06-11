"""Admin management endpoints (P0.4).

SUPER_ADMIN-only. Adds the path:
  - GET    /api/v1/admins             — list all admins
  - GET    /api/v1/admins/{id}        — read one
  - POST   /api/v1/admins             — create
  - PATCH  /api/v1/admins/{id}        — update (role, status, unlock, reset password)
  - DELETE /api/v1/admins/{id}        — soft-delete (is_active=False)

Safety rails:
  - A SUPER_ADMIN cannot delete or demote THEMSELVES (no single-point-of-lockout).
  - The system always has at least one ACTIVE SUPER_ADMIN — refuses operations
    that would leave none.
  - Username collisions surface as 409.
  - Initial password on creation is bcrypt-hashed immediately; never logged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db, require_roles
from app.core.constants import Role
from app.core.exceptions import (
    AlreadyExistsError,
    InvalidStateError,
    NotFoundError,
)
from app.core.logger import get_logger
from app.core.security import hash_password
from app.models.admin import Admin
from app.repositories.admin_repo import AdminRepository
from app.schemas.auth import AdminCreate, AdminRead, AdminUpdate
from app.services.auth_service import _record_audit
from app.utils.time_utils import now_utc

router = APIRouter(prefix="/admins", tags=["admins"])
log = get_logger(__name__)


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _count_active_super_admins(db: Session, *, excluding_id: int | None = None) -> int:
    """Used by safety rails — we never let the last active SUPER_ADMIN go."""
    stmt = select(Admin).where(
        Admin.role == Role.SUPER_ADMIN,
        Admin.is_active == True,  # noqa: E712
    )
    if excluding_id is not None:
        stmt = stmt.where(Admin.id != excluding_id)
    return len(db.execute(stmt).scalars().all())


@router.get("", response_model=list[AdminRead])
def list_admins(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> list[AdminRead]:
    stmt = select(Admin).order_by(Admin.id.asc())
    return [AdminRead.model_validate(a) for a in db.execute(stmt).scalars().all()]


@router.get("/{admin_id}", response_model=AdminRead)
def get_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> AdminRead:
    admin = AdminRepository(db).get(admin_id)
    if admin is None:
        raise NotFoundError(f"Admin {admin_id} not found")
    return AdminRead.model_validate(admin)


@router.post("", response_model=AdminRead, status_code=201)
def create_admin(
    payload: AdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> AdminRead:
    repo = AdminRepository(db)
    if repo.get_by_username(payload.username) is not None:
        raise AlreadyExistsError(f"Admin '{payload.username}' already exists")

    new_admin = Admin(
        username=payload.username,
        password_hash=hash_password(payload.initial_password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(new_admin)
    db.flush()

    _record_audit(
        db,
        admin_id=actor.id,
        action="ADMIN_CREATE",
        target_type="Admin",
        target_id=new_admin.id,
        source_ip=_client_ip(request),
        detail=f"username={new_admin.username} role={new_admin.role.value}",
    )
    log.info(
        "Admin id=%s created admin id=%s username=%s role=%s",
        actor.id, new_admin.id, new_admin.username, new_admin.role.value,
    )
    return AdminRead.model_validate(new_admin)


@router.patch("/{admin_id}", response_model=AdminRead)
def update_admin(
    admin_id: int,
    payload: AdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> AdminRead:
    repo = AdminRepository(db)
    admin = repo.get(admin_id)
    if admin is None:
        raise NotFoundError(f"Admin {admin_id} not found")

    data = payload.model_dump(exclude_unset=True)
    audit_detail_parts: list[str] = []

    # ---- Safety rails ----
    # Can't lock out the system: prevent demoting / deactivating the LAST
    # active SUPER_ADMIN.
    will_demote = (
        data.get("role") is not None
        and admin.role == Role.SUPER_ADMIN
        and data["role"] != Role.SUPER_ADMIN
    )
    will_deactivate = (
        data.get("is_active") is False and admin.is_active and admin.role == Role.SUPER_ADMIN
    )
    if will_demote or will_deactivate:
        remaining = _count_active_super_admins(db, excluding_id=admin.id)
        if remaining == 0:
            raise InvalidStateError(
                "Refusing — this would leave the system with no active SUPER_ADMIN. "
                "Promote another admin to SUPER_ADMIN first."
            )

    # Apply scalar updates
    if "full_name" in data:
        admin.full_name = data["full_name"]
        audit_detail_parts.append(f"full_name={data['full_name']!r}")
    if "role" in data and data["role"] is not None:
        old_role = admin.role.value
        admin.role = data["role"]
        audit_detail_parts.append(f"role:{old_role}->{admin.role.value}")
    if "is_active" in data and data["is_active"] is not None:
        if data["is_active"] != admin.is_active:
            audit_detail_parts.append(f"is_active:{admin.is_active}->{data['is_active']}")
        admin.is_active = data["is_active"]

    # Password reset — SUPER_ADMIN forces a new password for an admin
    # who forgot theirs. The target can log in with the new password and
    # rotate it themselves via /change-password.
    if data.get("reset_password"):
        admin.password_hash = hash_password(data["reset_password"])
        admin.password_changed_at = None
        audit_detail_parts.append("password_reset")

    db.flush()
    _record_audit(
        db,
        admin_id=actor.id,
        action="ADMIN_UPDATE",
        target_type="Admin",
        target_id=admin.id,
        source_ip=_client_ip(request),
        detail="; ".join(audit_detail_parts) if audit_detail_parts else "no-op",
    )
    return AdminRead.model_validate(admin)


@router.delete("/{admin_id}", status_code=204, response_model=None)
def deactivate_admin(
    admin_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> None:
    """Soft delete (is_active=False). Cannot remove yourself or the last super admin."""
    if admin_id == actor.id:
        raise InvalidStateError("You cannot deactivate yourself.")
    admin = AdminRepository(db).get(admin_id)
    if admin is None:
        raise NotFoundError(f"Admin {admin_id} not found")
    if admin.role == Role.SUPER_ADMIN:
        remaining = _count_active_super_admins(db, excluding_id=admin.id)
        if remaining == 0:
            raise InvalidStateError(
                "Refusing — this is the last active SUPER_ADMIN."
            )
    admin.is_active = False
    db.flush()
    _record_audit(
        db,
        admin_id=actor.id,
        action="ADMIN_DEACTIVATE",
        target_type="Admin",
        target_id=admin.id,
        source_ip=_client_ip(request),
        detail=f"username={admin.username}",
    )
