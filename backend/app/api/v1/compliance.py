"""DPDP compliance endpoints (P0.9 + P0.10).

  - POST   /api/v1/consent                     — record consent
  - GET    /api/v1/consent                     — list consent records (filter by employee/scope)
  - GET    /api/v1/consent/{id}                — read one
  - POST   /api/v1/consent/{id}/withdraw       — mark withdrawn
  - GET    /api/v1/consent/employee/{id}/status — quick status check per scope

  - POST   /api/v1/erasure/employee/{id}       — purge all biometric data (P0.10)
  - GET    /api/v1/erasure/log                 — paginated purge audit log

Safety rails:
  - Erasure requires SUPER_ADMIN.
  - Erasure refuses if confirmation_phrase != "ERASE <employee_code>"
    (defense-in-depth against accidental click).
  - Audit log row is written BEFORE files are deleted.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db, require_roles
from app.core.constants import Role
from app.core.exceptions import InvalidStateError, NotFoundError
from app.core.logger import get_logger
from app.db.session import session_scope
from app.models.admin import Admin
from app.models.compliance import (
    BiometricPurgeLog,
    ConsentRecord,
    ConsentScope,
)
from app.models.employee import Employee
from app.schemas.compliance import (
    BiometricPurgeRequest,
    BiometricPurgeResult,
    ConsentCreate,
    ConsentRead,
    ConsentWithdrawRequest,
    PurgeLogRead,
)
from app.services.compliance_service import (
    BiometricPurgeService,
    ConsentService,
)

router = APIRouter(tags=["compliance"])
log = get_logger(__name__)


# ---------- Consent endpoints ----------


@router.post("/consent", response_model=ConsentRead, status_code=201)
def record_consent(
    payload: ConsentCreate,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> ConsentRead:
    svc = ConsentService(db)
    row = svc.record(
        employee_id=payload.employee_id,
        subject_label=payload.subject_label,
        scope=payload.scope,
        consent_text=payload.consent_text,
        given_at=payload.given_at,
        given_by_admin=actor,
    )
    return ConsentRead.model_validate(row)


@router.get("/consent", response_model=list[ConsentRead])
def list_consent(
    employee_id: int | None = Query(default=None),
    scope: ConsentScope | None = Query(default=None),
    active_only: bool = Query(default=False, description="Only non-withdrawn"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[ConsentRead]:
    stmt = select(ConsentRecord).order_by(ConsentRecord.given_at.desc())
    if employee_id is not None:
        stmt = stmt.where(ConsentRecord.employee_id == employee_id)
    if scope is not None:
        stmt = stmt.where(ConsentRecord.scope == scope)
    if active_only:
        stmt = stmt.where(ConsentRecord.withdrawn_at.is_(None))
    stmt = stmt.limit(limit)
    return [ConsentRead.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.get("/consent/{consent_id}", response_model=ConsentRead)
def get_consent(
    consent_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> ConsentRead:
    row = db.get(ConsentRecord, consent_id)
    if row is None:
        raise NotFoundError(f"Consent {consent_id} not found")
    return ConsentRead.model_validate(row)


@router.post("/consent/{consent_id}/withdraw", response_model=ConsentRead)
def withdraw_consent(
    consent_id: int,
    payload: ConsentWithdrawRequest,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> ConsentRead:
    row = ConsentService(db).withdraw(consent_id, payload.withdrawn_reason, actor)
    return ConsentRead.model_validate(row)


@router.get("/consent/employee/{employee_id}/status")
def consent_status(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> dict:
    svc = ConsentService(db)
    return {
        "employee_id": employee_id,
        "biometric_capture_active": svc.is_active_for_employee(
            employee_id, ConsentScope.BIOMETRIC_CAPTURE
        ),
        "attendance_tracking_active": svc.is_active_for_employee(
            employee_id, ConsentScope.ATTENDANCE_TRACKING
        ),
    }


# ---------- Right-to-erasure ----------


@router.post(
    "/erasure/employee/{employee_id}",
    response_model=BiometricPurgeResult,
    status_code=200,
)
def erase_employee_biometrics(
    employee_id: int,
    payload: BiometricPurgeRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> BiometricPurgeResult:
    """Purge all biometric data for one employee. SUPER_ADMIN only.

    Required confirmation phrase: literal `ERASE <employee_code>`.
    """
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise NotFoundError(f"Employee {employee_id} not found")

    expected_phrase = f"ERASE {emp.employee_code}"
    if payload.confirmation_phrase != expected_phrase:
        raise InvalidStateError(
            f"Confirmation phrase mismatch. To proceed, send: {expected_phrase!r}"
        )

    svc = BiometricPurgeService(db)
    purge_row, files_to_unlink, anonymized = svc.purge(
        employee_id=employee_id,
        actor=actor,
        reason=payload.reason,
        delete_employee_row=payload.delete_employee_row,
        anonymize_attendance_events=payload.anonymize_attendance_events,
    )
    # Flush so we have the purge_row.id available after commit.
    db.flush()
    result = BiometricPurgeResult(
        employee_id=employee_id,
        employee_code=purge_row.employee_code,
        purged_at=purge_row.purged_at,
        embedding_count=purge_row.embedding_count,
        image_count=purge_row.image_count,
        snapshot_count=purge_row.snapshot_count,
        attendance_events_anonymized=purge_row.attendance_events_anonymized,
        employee_row_deleted=payload.delete_employee_row,
        purge_log_id=purge_row.id,
    )

    # Defer file deletion + cache reload to AFTER commit so a transaction
    # failure doesn't orphan files or leave the cache in a partial state.
    files_snapshot = list(files_to_unlink)

    def _post_commit() -> None:
        removed = BiometricPurgeService.unlink_files(files_snapshot)
        log.info(
            "Erasure files removed: %d of %d for purge_log_id=%s",
            removed, len(files_snapshot), purge_row.id,
        )
        # Reload the embedding cache so the deleted person's vectors
        # stop matching frames.
        try:
            cache = request.app.state.embedding_cache
            cache.load_from_db()
            log.info("Embedding cache reloaded after erasure")
        except Exception:
            log.exception("Failed to reload embedding cache after erasure")

    # Run AFTER the get_db dep commits. We use the request scope to
    # register an after-request hook via background_tasks pattern.
    # Simpler: just register on app's state and run synchronously here
    # — but that would happen BEFORE the get_db commit. The cleanest
    # solution is BackgroundTasks via FastAPI, but to avoid threading
    # complexity we explicitly commit here first, then run cleanup.
    db.commit()
    _post_commit()
    return result


@router.get("/erasure/log", response_model=list[PurgeLogRead])
def list_purge_log(
    employee_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> list[PurgeLogRead]:
    stmt = select(BiometricPurgeLog).order_by(BiometricPurgeLog.purged_at.desc())
    if employee_code:
        stmt = stmt.where(BiometricPurgeLog.employee_code == employee_code)
    stmt = stmt.limit(limit)
    return [PurgeLogRead.model_validate(r) for r in db.execute(stmt).scalars().all()]
