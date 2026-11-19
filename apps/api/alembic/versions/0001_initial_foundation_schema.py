"""Initial AgroDrone foundation schema.

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-11-19 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID, JSONVariant

revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "fields",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("crop_type", sa.String(length=100), nullable=True),
        sa.Column("area_hectares", sa.Float(), nullable=True),
        sa.Column("boundary_geojson", JSONVariant, nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("centroid_lng", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fields")),
    )
    op.create_index(op.f("ix_fields_name"), "fields", ["name"], unique=False)
    op.create_index(op.f("ix_fields_code"), "fields", ["code"], unique=True)

    op.create_table(
        "devices",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("device_type", sa.String(length=48), nullable=False),
        sa.Column("hardware_model", sa.String(length=160), nullable=False),
        sa.Column(
            "connectivity_mode", sa.String(length=32), nullable=False, server_default="isolated_ap"
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="registered"),
        sa.Column("local_ssid", sa.String(length=64), nullable=True),
        sa.Column("local_endpoint_url", sa.String(length=255), nullable=True),
        sa.Column("capabilities", JSONVariant, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
    )
    op.create_index(op.f("ix_devices_device_type"), "devices", ["device_type"], unique=False)

    op.create_table(
        "missions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("field_id", GUID(), nullable=True),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("operator_id", GUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_missions_device_id_devices"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["field_id"], ["fields.id"], name=op.f("fk_missions_field_id_fields"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"], ["users.id"], name=op.f("fk_missions_operator_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_missions")),
    )
    op.create_index(op.f("ix_missions_device_id"), "missions", ["device_id"], unique=False)
    op.create_index(op.f("ix_missions_field_id"), "missions", ["field_id"], unique=False)
    op.create_index(op.f("ix_missions_operator_id"), "missions", ["operator_id"], unique=False)
    op.create_index(op.f("ix_missions_status"), "missions", ["status"], unique=False)

    op.create_table(
        "media_assets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("mission_id", GUID(), nullable=True),
        sa.Column("field_id", GUID(), nullable=True),
        sa.Column("uploaded_by", GUID(), nullable=True),
        sa.Column("storage_backend", sa.String(length=16), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geo_lat", sa.Float(), nullable=True),
        sa.Column("geo_lng", sa.Float(), nullable=True),
        sa.Column("geo_source", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["field_id"], ["fields.id"], name=op.f("fk_media_assets_field_id_fields"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name=op.f("fk_media_assets_mission_id_missions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_media_assets_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_media_assets_storage_key")),
    )
    op.create_index(op.f("ix_media_assets_field_id"), "media_assets", ["field_id"], unique=False)
    op.create_index(op.f("ix_media_assets_mission_id"), "media_assets", ["mission_id"], unique=False)
    op.create_index(op.f("ix_media_assets_sha256"), "media_assets", ["sha256"], unique=False)

    op.create_table(
        "detection_jobs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("media_asset_id", GUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("dataset_scope", sa.String(length=120), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.35"),
        sa.Column("inference_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_detection_jobs_media_asset_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_jobs")),
    )
    op.create_index(
        op.f("ix_detection_jobs_media_asset_id"), "detection_jobs", ["media_asset_id"], unique=False
    )
    op.create_index(op.f("ix_detection_jobs_status"), "detection_jobs", ["status"], unique=False)

    op.create_table(
        "detection_items",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_x1", sa.Float(), nullable=False),
        sa.Column("bbox_y1", sa.Float(), nullable=False),
        sa.Column("bbox_x2", sa.Float(), nullable=False),
        sa.Column("bbox_y2", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["detection_jobs.id"],
            name=op.f("fk_detection_items_job_id_detection_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_items")),
    )
    op.create_index(op.f("ix_detection_items_job_id"), "detection_items", ["job_id"], unique=False)
    op.create_index(op.f("ix_detection_items_label"), "detection_items", ["label"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("field_id", GUID(), nullable=True),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("detection_job_id", GUID(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("acknowledged_by", GUID(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            name=op.f("fk_alerts_acknowledged_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["detection_job_id"],
            ["detection_jobs.id"],
            name=op.f("fk_alerts_detection_job_id_detection_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_alerts_device_id_devices"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["field_id"], ["fields.id"], name=op.f("fk_alerts_field_id_fields"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(op.f("ix_alerts_detection_job_id"), "alerts", ["detection_job_id"], unique=False)
    op.create_index(op.f("ix_alerts_device_id"), "alerts", ["device_id"], unique=False)
    op.create_index(op.f("ix_alerts_field_id"), "alerts", ["field_id"], unique=False)
    op.create_index(op.f("ix_alerts_severity"), "alerts", ["severity"], unique=False)
    op.create_index(op.f("ix_alerts_status"), "alerts", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("detection_items")
    op.drop_table("detection_jobs")
    op.drop_table("media_assets")
    op.drop_table("missions")
    op.drop_table("devices")
    op.drop_table("fields")
    op.drop_table("users")
