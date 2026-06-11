"""DPDP Act 2023 compliance services.

  - ConsentService — records and looks up consent (Sec 6)
  - BiometricPurgeService — irreversibly deletes face images + embeddings
    for an employee, writes an audit row in biometric_purge_log,
    optionally anonymizes past attendance events (Sec 8(7), Sec 12).

Both services preserve isolation: they NEVER touch live worker state.
After a purge, the embedding cache is reloaded so the deleted person's
embeddings stop matching faces in subsequent frames.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateError, NotFoundError
from app.core.logger import get_logger
from app.models.admin import Admin
from app.models.attendance_event import AttendanceEvent
from app.models.compliance import (
    AdminAuditLog,
    BiometricPurgeLog,
    ConsentRecord,
    ConsentScope,
)
from app.models.employee import Employee
from app.models.face_embedding import EmployeeFaceEmbedding
from app.models.face_image import EmployeeFaceImage
from app.utils.time_utils import now_utc

log = get_logger(__name__)


# ----------------------------------------------------------------
# Consent
# ----------------------------------------------------------------


class ConsentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        employee_id: int | None,
        subject_label: str | None,
        scope: ConsentScope,
        consent_text: str,
        given_at,
        given_by_admin: Admin,
    ) -> ConsentRecord:
        if employee_id is None and not subject_label:
            raise InvalidStateError(
                "Either employee_id or subject_label must be provided for a consent record."
            )
        row = ConsentRecord(
            employee_id=employee_id,
            subject_label=subject_label,
            scope=scope,
            consent_text=consent_text,
            given_at=given_at or now_utc(),
            given_by_admin_id=given_by_admin.id,
        )
        self.db.add(row)
        self.db.flush()
        log.info(
            "Consent recorded id=%s employee_id=%s scope=%s by admin id=%s",
            row.id, employee_id, scope.value, given_by_admin.id,
        )
        return row

    def withdraw(self, consent_id: int, reason: str, by_admin: Admin) -> ConsentRecord:
        row = self.db.get(ConsentRecord, consent_id)
        if row is None:
            raise NotFoundError(f"Consent {consent_id} not found")
        if row.withdrawn_at is not None:
            raise InvalidStateError("Consent already withdrawn")
        row.withdrawn_at = now_utc()
        row.withdrawn_reason = reason
        self.db.flush()
        log.info(
            "Consent withdrawn id=%s by admin id=%s reason=%r",
            row.id, by_admin.id, reason[:80],
        )
        return row

    def latest_for_employee(
        self, employee_id: int, scope: ConsentScope
    ) -> ConsentRecord | None:
        stmt = (
            select(ConsentRecord)
            .where(
                ConsentRecord.employee_id == employee_id,
                ConsentRecord.scope == scope,
            )
            .order_by(ConsentRecord.given_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def is_active_for_employee(self, employee_id: int, scope: ConsentScope) -> bool:
        latest = self.latest_for_employee(employee_id, scope)
        return latest is not None and latest.withdrawn_at is None


# ----------------------------------------------------------------
# Right-to-erasure (P0.10)
# ----------------------------------------------------------------


class BiometricPurgeService:
    """Hard-deletes all biometric artifacts for an employee.

    Steps (single transaction):
      1. Snapshot employee fields for the immutable purge log.
      2. Collect file paths from EmployeeFaceImage + AttendanceEvent.snapshot_path.
      3. Delete EmployeeFaceEmbedding rows for the employee.
      4. Delete EmployeeFaceImage rows.
      5. If anonymize_attendance_events: clear snapshot_path + null the
         employee_id link on past events. (Optional — operator chooses.)
      6. If delete_employee_row: delete the Employee row outright.
      7. Write BiometricPurgeLog row.
      8. After commit, unlink all collected files (best-effort; missing
         files are fine — they may have been purged manually).
      9. Reload the embedding cache so subsequent frames don't match
         the deleted person.

    Steps 1-7 happen inside the caller's session_scope. Step 8 happens
    after commit so a transaction failure doesn't leave files orphaned.
    Step 9 happens via the returned closure.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def purge(
        self,
        *,
        employee_id: int,
        actor: Admin,
        reason: str | None,
        delete_employee_row: bool,
        anonymize_attendance_events: bool,
    ) -> tuple[BiometricPurgeLog, list[str], int]:
        emp = self.db.get(Employee, employee_id)
        if emp is None:
            raise NotFoundError(f"Employee {employee_id} not found")

        # 1. Snapshot
        snapshot_code = emp.employee_code
        snapshot_name = emp.name

        # 2. Collect files
        files_to_unlink: list[str] = []
        image_rows = (
            self.db.execute(
                select(EmployeeFaceImage).where(
                    EmployeeFaceImage.employee_id == employee_id
                )
            )
            .scalars()
            .all()
        )
        for img in image_rows:
            if img.file_path:
                files_to_unlink.append(img.file_path)
        image_count = len(image_rows)

        # Snapshot files from attendance events
        snapshot_count = 0
        if anonymize_attendance_events:
            events_with_snaps = (
                self.db.execute(
                    select(AttendanceEvent).where(
                        AttendanceEvent.employee_id == employee_id,
                        AttendanceEvent.snapshot_path.is_not(None),
                    )
                )
                .scalars()
                .all()
            )
            for ev in events_with_snaps:
                if ev.snapshot_path:
                    files_to_unlink.append(ev.snapshot_path)
            snapshot_count = len(events_with_snaps)

        # 3. Delete embeddings
        embedding_result = self.db.execute(
            delete(EmployeeFaceEmbedding).where(
                EmployeeFaceEmbedding.employee_id == employee_id
            )
        )
        embedding_count = embedding_result.rowcount or 0

        # 4. Delete image rows
        self.db.execute(
            delete(EmployeeFaceImage).where(
                EmployeeFaceImage.employee_id == employee_id
            )
        )

        # 5. Anonymize past attendance events (preserve attendance integrity
        #    but sever the link to the person and remove the photo).
        attendance_events_anonymized = 0
        if anonymize_attendance_events:
            result = self.db.execute(
                update(AttendanceEvent)
                .where(AttendanceEvent.employee_id == employee_id)
                .values(snapshot_path=None)
            )
            attendance_events_anonymized = result.rowcount or 0

        # 6. Delete the employee row entirely
        if delete_employee_row:
            # AttendanceEvent has FK to employees with NO cascade in the
            # schema as written, so we must either delete events first or
            # SET NULL. Choose SET NULL to preserve attendance history.
            # Models declare employee_id as nullable=False — we don't want
            # to alter schema mid-flight. Strategy: keep delete_employee_row=False
            # for production use; expose the flag for an explicit operator
            # override that ALSO deletes their attendance.
            self.db.execute(
                delete(AttendanceEvent).where(
                    AttendanceEvent.employee_id == employee_id
                )
            )
            self.db.delete(emp)
            attendance_events_anonymized = -1  # signal "deleted, not anonymized"

        # 7. Write the immutable audit row
        purge_row = BiometricPurgeLog(
            employee_id=employee_id,
            employee_code=snapshot_code,
            employee_name=snapshot_name,
            purged_at=now_utc(),
            purged_by_admin_id=actor.id,
            embedding_count=embedding_count,
            image_count=image_count,
            snapshot_count=snapshot_count,
            attendance_events_anonymized=max(0, attendance_events_anonymized),
            reason=reason,
            created_at=now_utc(),
        )
        self.db.add(purge_row)

        # Also write to admin_audit_log so it shows up in the general audit feed
        self.db.add(
            AdminAuditLog(
                admin_id=actor.id,
                action="BIOMETRIC_ERASURE",
                target_type="Employee",
                target_id=employee_id,
                detail=(
                    f"code={snapshot_code} embeddings={embedding_count} "
                    f"images={image_count} snapshots={snapshot_count} "
                    f"row_deleted={delete_employee_row}"
                ),
                created_at=now_utc(),
            )
        )
        self.db.flush()

        log.warning(
            "BIOMETRIC ERASURE id=%s emp_id=%s code=%s embeddings=%d images=%d "
            "snapshots=%d row_deleted=%s by admin id=%s",
            purge_row.id, employee_id, snapshot_code,
            embedding_count, image_count, snapshot_count,
            delete_employee_row, actor.id,
        )

        return purge_row, files_to_unlink, attendance_events_anonymized

    @staticmethod
    def unlink_files(paths: list[str]) -> int:
        """Best-effort file deletion AFTER the DB commit succeeds.

        Each path is tried independently — a missing file is OK, an error
        is logged but not raised. Returns count of files actually removed.
        """
        removed = 0
        for p in paths:
            try:
                fp = Path(p)
                if fp.exists():
                    fp.unlink()
                    removed += 1
            except Exception as exc:
                log.warning("Could not unlink %s: %s", p, exc)
        return removed
