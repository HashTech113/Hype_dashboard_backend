"""add unknown face clusters and captures + capture-pipeline settings

Revision ID: 0005_unknown_faces
Revises: 0004_settings_extras
Create Date: 2026-04-25

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_unknown_faces"
down_revision = "0004_settings_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # unknown_face_clusters
    # ------------------------------------------------------------------
    op.create_table(
        "unknown_face_clusters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("centroid", sa.LargeBinary(), nullable=False),
        sa.Column("centroid_dim", sa.Integer(), nullable=False, server_default="512"),
        sa.Column(
            "model_name",
            sa.String(length=64),
            nullable=False,
            server_default="buffalo_l",
        ),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROMOTED",
                "IGNORED",
                "MERGED",
                name="unknown_cluster_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("promoted_employee_id", sa.Integer(), nullable=True),
        sa.Column("merged_into_cluster_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["promoted_employee_id"],
            ["employees.id"],
            name="fk_unknown_face_clusters_promoted_employee_id_employees",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_cluster_id"],
            ["unknown_face_clusters.id"],
            # Short explicit name — the auto-generated 70-char name
            # exceeds Postgres' 63-char identifier limit.
            name="fk_unknown_clusters_merged_into",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_unknown_face_clusters"),
    )
    op.create_index(
        "ix_unknown_face_clusters_status",
        "unknown_face_clusters",
        ["status"],
    )
    op.create_index(
        "ix_unknown_face_clusters_last_seen_at",
        "unknown_face_clusters",
        ["last_seen_at"],
    )
    op.create_index(
        "ix_unknown_face_clusters_promoted_employee_id",
        "unknown_face_clusters",
        ["promoted_employee_id"],
    )
    op.create_index(
        "ix_unknown_face_clusters_status_last_seen",
        "unknown_face_clusters",
        ["status", "last_seen_at"],
    )

    # ------------------------------------------------------------------
    # unknown_face_captures
    # ------------------------------------------------------------------
    op.create_table(
        "unknown_face_captures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False, server_default="512"),
        sa.Column(
            "model_name",
            sa.String(length=64),
            nullable=False,
            server_default="buffalo_l",
        ),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("bbox_x", sa.Integer(), nullable=False),
        sa.Column("bbox_y", sa.Integer(), nullable=False),
        sa.Column("bbox_w", sa.Integer(), nullable=False),
        sa.Column("bbox_h", sa.Integer(), nullable=False),
        sa.Column("det_score", sa.Float(), nullable=False),
        sa.Column(
            "sharpness_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("KEEP", "DISCARDED", name="unknown_capture_status"),
            nullable=False,
            server_default="KEEP",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["unknown_face_clusters.id"],
            name="fk_unknown_face_captures_cluster_id_unknown_face_clusters",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["cameras.id"],
            name="fk_unknown_face_captures_camera_id_cameras",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_unknown_face_captures"),
    )
    op.create_index(
        "ix_unknown_face_captures_cluster_id",
        "unknown_face_captures",
        ["cluster_id"],
    )
    op.create_index(
        "ix_unknown_face_captures_captured_at",
        "unknown_face_captures",
        ["captured_at"],
    )
    op.create_index(
        "ix_unknown_face_captures_status",
        "unknown_face_captures",
        ["status"],
    )
    op.create_index(
        "ix_unknown_face_captures_cluster_time",
        "unknown_face_captures",
        ["cluster_id", "captured_at"],
    )

    # ------------------------------------------------------------------
    # attendance_settings additions (8 columns)
    # ------------------------------------------------------------------
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_capture_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_min_face_quality",
            sa.Float(),
            nullable=False,
            server_default="0.65",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_min_face_size_px",
            sa.Integer(),
            nullable=False,
            server_default="80",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_min_sharpness",
            sa.Float(),
            nullable=False,
            server_default="50.0",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_capture_cooldown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_cluster_match_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.55",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_max_total_captures",
            sa.Integer(),
            nullable=False,
            server_default="5000",
        ),
    )
    op.add_column(
        "attendance_settings",
        sa.Column(
            "unknown_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("attendance_settings", "unknown_retention_days")
    op.drop_column("attendance_settings", "unknown_max_total_captures")
    op.drop_column("attendance_settings", "unknown_cluster_match_threshold")
    op.drop_column("attendance_settings", "unknown_capture_cooldown_seconds")
    op.drop_column("attendance_settings", "unknown_min_sharpness")
    op.drop_column("attendance_settings", "unknown_min_face_size_px")
    op.drop_column("attendance_settings", "unknown_min_face_quality")
    op.drop_column("attendance_settings", "unknown_capture_enabled")

    op.drop_index(
        "ix_unknown_face_captures_cluster_time",
        table_name="unknown_face_captures",
    )
    op.drop_index("ix_unknown_face_captures_status", table_name="unknown_face_captures")
    op.drop_index(
        "ix_unknown_face_captures_captured_at", table_name="unknown_face_captures"
    )
    op.drop_index(
        "ix_unknown_face_captures_cluster_id", table_name="unknown_face_captures"
    )
    op.drop_table("unknown_face_captures")
    op.execute("DROP TYPE IF EXISTS unknown_capture_status")

    op.drop_index(
        "ix_unknown_face_clusters_status_last_seen",
        table_name="unknown_face_clusters",
    )
    op.drop_index(
        "ix_unknown_face_clusters_promoted_employee_id",
        table_name="unknown_face_clusters",
    )
    op.drop_index(
        "ix_unknown_face_clusters_last_seen_at",
        table_name="unknown_face_clusters",
    )
    op.drop_index(
        "ix_unknown_face_clusters_status",
        table_name="unknown_face_clusters",
    )
    op.drop_table("unknown_face_clusters")
    op.execute("DROP TYPE IF EXISTS unknown_cluster_status")
