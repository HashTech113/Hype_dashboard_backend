"""add early_exit_grace_minutes + default office hours 09:30-18:30

Revision ID: 0004_settings_defaults_and_early_grace
Revises: 0003_daily_attendance_extensions
Create Date: 2026-04-24

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_settings_extras"
down_revision = "0003_daily_attendance_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_settings",
        sa.Column(
            "early_exit_grace_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        "UPDATE attendance_settings "
        "SET work_start_time = COALESCE(work_start_time, TIME '09:30:00'), "
        "    work_end_time   = COALESCE(work_end_time,   TIME '18:30:00') "
        "WHERE id = 1"
    )


def downgrade() -> None:
    op.drop_column("attendance_settings", "early_exit_grace_minutes")
    # intentionally leave work_start_time / work_end_time values as-is on downgrade
