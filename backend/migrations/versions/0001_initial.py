"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=True),
        sa.Column(
            "role",
            sa.Enum("SUPER_ADMIN", "ADMIN", "VIEWER", name="admin_role"),
            nullable=False,
            server_default="ADMIN",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_admins"),
        sa.UniqueConstraint("username", name="uq_admins_username"),
    )
    op.create_index("ix_admins_username", "admins", ["username"])

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("designation", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_employees"),
        sa.UniqueConstraint("employee_code", name="uq_employees_employee_code"),
    )
    op.create_index("ix_employees_employee_code", "employees", ["employee_code"])
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_department", "employees", ["department"])
    op.create_index("ix_employees_is_active", "employees", ["is_active"])

    op.create_table(
        "employee_face_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_face_images_employee_id_employees",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["admins.id"],
            name="fk_employee_face_images_uploaded_by_admins",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_face_images"),
    )
    op.create_index("ix_employee_face_images_employee_id", "employee_face_images", ["employee_id"])
    op.create_index("ix_employee_face_images_file_hash", "employee_face_images", ["file_hash"])

    op.create_table(
        "employee_face_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default="512"),
        sa.Column("model_name", sa.String(length=64), nullable=False, server_default="buffalo_l"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_face_embeddings_employee_id_employees",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["employee_face_images.id"],
            name="fk_employee_face_embeddings_image_id_employee_face_images",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_face_embeddings"),
    )
    op.create_index(
        "ix_employee_face_embeddings_employee_id",
        "employee_face_embeddings",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_face_embeddings_image_id",
        "employee_face_embeddings",
        ["image_id"],
    )
    op.create_index(
        "ix_employee_face_embeddings_employee_model",
        "employee_face_embeddings",
        ["employee_id", "model_name"],
    )

    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rtsp_url", sa.String(length=1024), nullable=False),
        sa.Column(
            "camera_type",
            sa.Enum("ENTRY", "EXIT", name="camera_type"),
            nullable=False,
        ),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_cameras"),
        sa.UniqueConstraint("name", name="uq_cameras_name"),
    )
    op.create_index("ix_cameras_camera_type", "cameras", ["camera_type"])
    op.create_index("ix_cameras_is_active", "cameras", ["is_active"])

    op.create_table(
        "attendance_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum("IN", "BREAK_OUT", "BREAK_IN", "OUT", name="event_type"),
            nullable=False,
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("snapshot_path", sa.String(length=1024), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("corrected_by", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_attendance_events_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["cameras.id"],
            name="fk_attendance_events_camera_id_cameras",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["corrected_by"],
            ["admins.id"],
            name="fk_attendance_events_corrected_by_admins",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_events"),
    )
    op.create_index(
        "ix_attendance_events_employee_time",
        "attendance_events",
        ["employee_id", "event_time"],
    )
    op.create_index("ix_attendance_events_event_time", "attendance_events", ["event_time"])
    op.create_index(
        "ix_attendance_events_employee_type_time",
        "attendance_events",
        ["employee_id", "event_type", "event_time"],
    )
    op.create_index("ix_attendance_events_is_manual", "attendance_events", ["is_manual"])

    op.create_table(
        "daily_attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("in_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_out_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_in_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("out_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_work_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_break_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("PRESENT", "INCOMPLETE", "ABSENT", name="session_status"),
            nullable=False,
            server_default="ABSENT",
        ),
        sa.Column(
            "is_manually_adjusted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_daily_attendance_employee_id_employees",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_attendance"),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_daily_attendance_employee_date"),
    )
    op.create_index("ix_daily_attendance_employee_id", "daily_attendance", ["employee_id"])
    op.create_index("ix_daily_attendance_work_date", "daily_attendance", ["work_date"])
    op.create_index(
        "ix_daily_attendance_date_status",
        "daily_attendance",
        ["work_date", "status"],
    )

    op.create_table(
        "attendance_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("face_match_threshold", sa.Float(), nullable=False, server_default="0.45"),
        sa.Column("face_min_quality", sa.Float(), nullable=False, server_default="0.50"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("camera_fps", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("train_min_images", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("train_max_images", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("work_start_time", sa.Time(), nullable=True),
        sa.Column("work_end_time", sa.Time(), nullable=True),
        sa.Column("grace_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["admins.id"],
            name="fk_attendance_settings_updated_by_admins",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_settings"),
        sa.CheckConstraint("id = 1", name="ck_attendance_settings_singleton"),
    )
    op.execute(
        "INSERT INTO attendance_settings (id, face_match_threshold, face_min_quality, "
        "cooldown_seconds, camera_fps, train_min_images, train_max_images, "
        "work_start_time, work_end_time, grace_minutes) "
        "VALUES (1, 0.45, 0.50, 5, 1, 5, 20, TIME '09:30:00', TIME '18:30:00', 0)"
    )


def downgrade() -> None:
    op.drop_table("attendance_settings")

    op.drop_index("ix_daily_attendance_date_status", table_name="daily_attendance")
    op.drop_index("ix_daily_attendance_work_date", table_name="daily_attendance")
    op.drop_index("ix_daily_attendance_employee_id", table_name="daily_attendance")
    op.drop_table("daily_attendance")

    op.drop_index("ix_attendance_events_is_manual", table_name="attendance_events")
    op.drop_index("ix_attendance_events_employee_type_time", table_name="attendance_events")
    op.drop_index("ix_attendance_events_event_time", table_name="attendance_events")
    op.drop_index("ix_attendance_events_employee_time", table_name="attendance_events")
    op.drop_table("attendance_events")

    op.drop_index("ix_cameras_is_active", table_name="cameras")
    op.drop_index("ix_cameras_camera_type", table_name="cameras")
    op.drop_table("cameras")

    op.drop_index("ix_employee_face_embeddings_employee_model", table_name="employee_face_embeddings")
    op.drop_index("ix_employee_face_embeddings_image_id", table_name="employee_face_embeddings")
    op.drop_index("ix_employee_face_embeddings_employee_id", table_name="employee_face_embeddings")
    op.drop_table("employee_face_embeddings")

    op.drop_index("ix_employee_face_images_file_hash", table_name="employee_face_images")
    op.drop_index("ix_employee_face_images_employee_id", table_name="employee_face_images")
    op.drop_table("employee_face_images")

    op.drop_index("ix_employees_is_active", table_name="employees")
    op.drop_index("ix_employees_department", table_name="employees")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_index("ix_employees_employee_code", table_name="employees")
    op.drop_table("employees")

    op.drop_index("ix_admins_username", table_name="admins")
    op.drop_table("admins")

    sa.Enum(name="session_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="camera_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="admin_role").drop(op.get_bind(), checkfirst=True)
