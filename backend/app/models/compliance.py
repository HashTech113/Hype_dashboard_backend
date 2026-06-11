"""DPDP Act 2023 compliance models.

  - ConsentRecord — Sec 6 explicit consent capture
  - BiometricPurgeLog — Sec 12 right-to-erasure audit trail (immutable)
  - AdminAuditLog — Sec 8 + general security audit (immutable)
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ConsentScope(str, enum.Enum):
    BIOMETRIC_CAPTURE = "BIOMETRIC_CAPTURE"
    ATTENDANCE_TRACKING = "ATTENDANCE_TRACKING"
    UNKNOWN_VISITOR_CAPTURE = "UNKNOWN_VISITOR_CAPTURE"


class ConsentRecord(Base, TimestampMixin):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL", name="fk_consent_employee"),
        nullable=True,
        index=True,
    )
    # For non-employee consent (e.g. signed visitor consent batch)
    subject_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scope: Mapped[ConsentScope] = mapped_column(
        SAEnum(ConsentScope, name="consent_scope"), nullable=False, index=True
    )
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    given_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", name="fk_consent_given_by"), nullable=False
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BiometricPurgeLog(Base):
    """Immutable audit trail. NO FK on employee_id — log outlives row."""
    __tablename__ = "biometric_purge_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(Integer, nullable=False)  # snapshot
    employee_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(128), nullable=False)
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    purged_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", name="fk_purge_log_admin"), nullable=False
    )
    embedding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attendance_events_anonymized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAuditLog(Base):
    """Immutable. No FK on admin_id — log outlives the admin row."""
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
