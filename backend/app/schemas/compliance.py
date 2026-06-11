"""DPDP-compliance schemas (consent records + purge log)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.compliance import ConsentScope
from app.schemas.common import ORMModel


class ConsentCreate(BaseModel):
    employee_id: int | None = None
    subject_label: str | None = Field(default=None, max_length=256)
    scope: ConsentScope
    consent_text: str = Field(min_length=10, max_length=10_000)
    # Optional explicit timestamp — if omitted, server uses now_utc().
    given_at: datetime | None = None


class ConsentRead(ORMModel):
    id: int
    employee_id: int | None
    subject_label: str | None
    scope: ConsentScope
    consent_text: str
    given_at: datetime
    given_by_admin_id: int
    withdrawn_at: datetime | None
    withdrawn_reason: str | None
    created_at: datetime


class ConsentWithdrawRequest(BaseModel):
    withdrawn_reason: str = Field(min_length=1, max_length=5_000)


class BiometricPurgeRequest(BaseModel):
    # Confirm intent — frontend must echo back "ERASE <employee_code>" to avoid
    # accidental purges. Defense in depth alongside SUPER_ADMIN role gating.
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=5_000)
    # Whether to also delete the underlying Employee row (full erasure)
    # vs only the biometric artifacts (DPDP "purpose fulfilled" case).
    delete_employee_row: bool = False
    # Whether to anonymize past attendance events. Default True to honor
    # right-to-erasure even for derived data.
    anonymize_attendance_events: bool = True


class BiometricPurgeResult(BaseModel):
    employee_id: int
    employee_code: str
    purged_at: datetime
    embedding_count: int
    image_count: int
    snapshot_count: int
    attendance_events_anonymized: int
    employee_row_deleted: bool
    purge_log_id: int


class PurgeLogRead(ORMModel):
    id: int
    employee_id: int
    employee_code: str
    employee_name: str
    purged_at: datetime
    purged_by_admin_id: int
    embedding_count: int
    image_count: int
    snapshot_count: int
    attendance_events_anonymized: int
    reason: str | None
