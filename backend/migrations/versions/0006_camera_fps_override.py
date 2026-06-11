"""add per-camera fps override + worker resilience columns

Adds:
  - cameras.fps_override (INT NULL) — per-camera FPS, NULL = use global setting

Revision ID: 0006_camera_fps_override
Revises: 0005_unknown_faces
Create Date: 2026-06-06

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_camera_fps_override"
down_revision = "0005_unknown_faces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable so existing rows are preserved. CHECK constraint enforces a
    # sensible range (1..30) at the database level — defense in depth, since
    # Pydantic already validates the same range at the API boundary.
    op.add_column(
        "cameras",
        sa.Column("fps_override", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_cameras_fps_override_range",
        "cameras",
        "fps_override IS NULL OR (fps_override >= 1 AND fps_override <= 30)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cameras_fps_override_range", "cameras", type_="check")
    op.drop_column("cameras", "fps_override")
