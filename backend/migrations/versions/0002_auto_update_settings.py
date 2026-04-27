"""add auto-update fields to attendance_settings

Revision ID: 0002_auto_update_settings
Revises: 0001_initial
Create Date: 2026-04-24

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_auto_update_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_settings",
        sa.Column(
            "auto_update_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "auto_update_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.70",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "auto_update_cooldown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="3600",
        ),
    )


def downgrade() -> None:
    op.drop_column("attendance_settings", "auto_update_cooldown_seconds")
    op.drop_column("attendance_settings", "auto_update_threshold")
    op.drop_column("attendance_settings", "auto_update_enabled")
