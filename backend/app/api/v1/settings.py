from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.constants import Role
from app.models.admin import Admin
from app.repositories.settings_repo import SettingsRepository
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services.settings_service import get_settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def get_current_settings(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.VIEWER)),
) -> SettingsRead:
    row = SettingsRepository(db).get()
    return SettingsRead.model_validate(row)


@router.patch("", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> SettingsRead:
    data = payload.model_dump(exclude_unset=True)
    get_settings_service().update(data, admin_id=admin.id)
    row = SettingsRepository(db).get()
    return SettingsRead.model_validate(row)
