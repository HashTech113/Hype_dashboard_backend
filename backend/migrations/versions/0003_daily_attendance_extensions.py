"""add break_count, late/early minutes, is_day_closed to daily_attendance

Revision ID: 0003_daily_attendance_extensions
Revises: 0002_auto_update_settings
Create Date: 2026-04-24

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_daily_attendance_extensions"
down_revision = "0002_auto_update_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_attendance",
        sa.Column("break_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_attendance",
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_attendance",
        sa.Column(
            "early_exit_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "daily_attendance",
        sa.Column(
            "is_day_closed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("daily_attendance", "is_day_closed")
    op.drop_column("daily_attendance", "early_exit_minutes")
    op.drop_column("daily_attendance", "late_minutes")
    op.drop_column("daily_attendance", "break_count")
