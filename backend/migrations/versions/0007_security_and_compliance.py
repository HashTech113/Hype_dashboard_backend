"""security + DPDP compliance hardening

Adds:
  - admins.must_change_password (BOOL, default FALSE) — force-rotate flag for new admins
  - admins.password_changed_at (TIMESTAMPTZ, nullable) — last password rotation
  - admins.failed_attempts (INT, default 0) — brute-force attempt counter
  - admins.locked_until (TIMESTAMPTZ, nullable) — lockout window end
  - consent_records (new table) — DPDP Sec 6 consent capture per employee
  - biometric_purge_log (new table) — audit trail for DPDP Sec 12 right-to-erasure
  - admin_audit_log (new table) — who-did-what tracking for sensitive actions

Isolation guarantees (per user requirement: "every single thing should work
without interfering with others"):
  - All new columns nullable with safe defaults — no existing row gets a
    new constraint failure.
  - must_change_password defaults FALSE on existing admins (they were
    already operating with their current password — we trust them; new
    admins from this migration onward get TRUE).
  - failed_attempts defaults 0; locked_until defaults NULL — existing
    sessions unaffected.
  - All new tables have only INSERT-side relationships; no FK adds to
    pre-existing tables that could fail on stale data.

Revision ID: 0007_security_and_compliance
Revises: 0006_camera_fps_override
Create Date: 2026-06-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_security_and_compliance"
down_revision = "0006_camera_fps_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- admins: new columns ------------------------------------------------
    # Add with SERVER-side defaults so existing rows pick them up immediately
    # without a separate UPDATE pass (faster on a large admins table).
    op.add_column(
        "admins",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "admins",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "admins",
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "admins",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # --- consent_records (DPDP Sec 6) --------------------------------------
    # Let op.create_table create the consent_scope enum implicitly. If a
    # prior failed run left the type behind, the downgrade() path or a
    # manual `DROP TYPE consent_scope;` clears it.
    consent_scope = sa.Enum(
        "BIOMETRIC_CAPTURE",
        "ATTENDANCE_TRACKING",
        "UNKNOWN_VISITOR_CAPTURE",
        name="consent_scope",
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),  # nullable for visitor consent
        sa.Column("subject_label", sa.String(256), nullable=True),  # e.g. "visitor batch 2026-06"
        sa.Column("scope", consent_scope, nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("given_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # FKs — admin should exist; employee may be nullable
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], name="fk_consent_employee", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["given_by_admin_id"], ["admins.id"], name="fk_consent_given_by"),
    )
    op.create_index("ix_consent_employee_id", "consent_records", ["employee_id"])
    op.create_index("ix_consent_scope", "consent_records", ["scope"])
    op.create_index("ix_consent_given_at", "consent_records", ["given_at"])

    # --- biometric_purge_log (DPDP Sec 12 audit trail) ---------------------
    # NOTE: employee_id is INT but NO FK — because we want the log row to
    # outlive the employee row when the purge actually deletes the employee.
    op.create_table(
        "biometric_purge_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),  # snapshot of pre-purge id
        sa.Column("employee_code", sa.String(64), nullable=False),  # snapshot for audit
        sa.Column("employee_name", sa.String(128), nullable=False),  # snapshot for audit
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("purged_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("embedding_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attendance_events_anonymized", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["purged_by_admin_id"], ["admins.id"], name="fk_purge_log_admin"),
    )
    op.create_index("ix_purge_log_employee_code", "biometric_purge_log", ["employee_code"])
    op.create_index("ix_purge_log_purged_at", "biometric_purge_log", ["purged_at"])

    # --- admin_audit_log (general who-did-what for sensitive actions) ------
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), nullable=True),  # nullable for system actions
        sa.Column("action", sa.String(64), nullable=False),  # LOGIN_SUCCESS, LOGIN_FAILED, ADMIN_CREATE, ROLE_CHANGE, ...
        sa.Column("target_type", sa.String(32), nullable=True),  # "Admin", "Employee", "Camera"
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # No FK on admin_id — even if the admin row is deleted, the log row
        # must remain (DPDP audit requirement).
    )
    op.create_index("ix_audit_log_admin_id", "admin_audit_log", ["admin_id"])
    op.create_index("ix_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "admin_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_audit_log_action", table_name="admin_audit_log")
    op.drop_index("ix_audit_log_admin_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_index("ix_purge_log_purged_at", table_name="biometric_purge_log")
    op.drop_index("ix_purge_log_employee_code", table_name="biometric_purge_log")
    op.drop_table("biometric_purge_log")

    op.drop_index("ix_consent_given_at", table_name="consent_records")
    op.drop_index("ix_consent_scope", table_name="consent_records")
    op.drop_index("ix_consent_employee_id", table_name="consent_records")
    op.drop_table("consent_records")
    sa.Enum(name="consent_scope").drop(op.get_bind(), checkfirst=True)

    op.drop_column("admins", "locked_until")
    op.drop_column("admins", "failed_attempts")
    op.drop_column("admins", "password_changed_at")
    op.drop_column("admins", "must_change_password")
