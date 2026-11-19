"""Phase 3 AgroVision AI Engine: detection job provenance, video frame sampling, human review, and registered datasets.

Revision ID: 0003_phase3_agrovision_ai_engine
Revises: 0002_phase2_core_operations
Create Date: 2026-11-19 16:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID, JSONVariant

revision: str = "0003_phase3_agrovision_ai_engine"
down_revision: str | None = "0002_phase2_core_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registered_datasets",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("detection_mode", sa.String(length=48), nullable=False),
        sa.Column("classes_json", JSONVariant, nullable=False),
        sa.Column("train_count", sa.Integer(), nullable=False),
        sa.Column("val_count", sa.Integer(), nullable=False),
        sa.Column("test_count", sa.Integer(), nullable=False),
        sa.Column("metrics_json", JSONVariant, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_registered_datasets_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registered_datasets")),
    )
    op.create_index(
        op.f("ix_registered_datasets_owner_id"), "registered_datasets", ["owner_id"], unique=False
    )
    op.create_index(
        op.f("ix_registered_datasets_name"), "registered_datasets", ["name"], unique=True
    )
    op.create_index(
        op.f("ix_registered_datasets_detection_mode"),
        "registered_datasets",
        ["detection_mode"],
        unique=False,
    )

    with op.batch_alter_table("detection_jobs") as batch_op:
        batch_op.add_column(sa.Column("owner_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("field_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("mission_id", GUID(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "detection_mode", sa.String(length=48), nullable=False, server_default="general"
            )
        )
        batch_op.add_column(
            sa.Column(
                "model_id",
                sa.String(length=80),
                nullable=False,
                server_default="yolov8n-coco-general",
            )
        )
        batch_op.add_column(
            sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("media_type", sa.String(length=16), nullable=False, server_default="image")
        )
        batch_op.add_column(sa.Column("model_checksum", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("device_used", sa.String(length=32), nullable=False, server_default="cpu")
        )
        batch_op.add_column(sa.Column("frame_sample_interval_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("max_frames", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("total_frames_sampled", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("video_duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("annotated_storage_key", sa.String(length=512), nullable=True)
        )
        batch_op.add_column(
            sa.Column("summary_json", JSONVariant, nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_detection_jobs_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            op.f("fk_detection_jobs_field_id_fields"),
            "fields",
            ["field_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            op.f("fk_detection_jobs_mission_id_missions"),
            "missions",
            ["mission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_detection_jobs_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(op.f("ix_detection_jobs_field_id"), ["field_id"], unique=False)
        batch_op.create_index(op.f("ix_detection_jobs_mission_id"), ["mission_id"], unique=False)
        batch_op.create_index(
            op.f("ix_detection_jobs_detection_mode"), ["detection_mode"], unique=False
        )
        batch_op.create_index(op.f("ix_detection_jobs_model_id"), ["model_id"], unique=False)

    with op.batch_alter_table("detection_items") as batch_op:
        batch_op.add_column(sa.Column("class_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("original_label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("original_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("frame_index", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("timestamp_ms", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("annotated_frame_storage_key", sa.String(length=512), nullable=True)
        )
        batch_op.add_column(sa.Column("reviewer_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reviewer_notes", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_detection_items_reviewer_id_users"),
            "users",
            ["reviewer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_detection_items_review_status"), ["review_status"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("detection_items") as batch_op:
        batch_op.drop_index(op.f("ix_detection_items_review_status"))
        batch_op.drop_constraint(op.f("fk_detection_items_reviewer_id_users"), type_="foreignkey")
        batch_op.drop_column("reviewer_notes")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewer_id")
        batch_op.drop_column("annotated_frame_storage_key")
        batch_op.drop_column("timestamp_ms")
        batch_op.drop_column("frame_index")
        batch_op.drop_column("original_confidence")
        batch_op.drop_column("original_label")
        batch_op.drop_column("class_id")

    with op.batch_alter_table("detection_jobs") as batch_op:
        batch_op.drop_index(op.f("ix_detection_jobs_model_id"))
        batch_op.drop_index(op.f("ix_detection_jobs_detection_mode"))
        batch_op.drop_index(op.f("ix_detection_jobs_mission_id"))
        batch_op.drop_index(op.f("ix_detection_jobs_field_id"))
        batch_op.drop_index(op.f("ix_detection_jobs_owner_id"))
        batch_op.drop_constraint(op.f("fk_detection_jobs_mission_id_missions"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_detection_jobs_field_id_fields"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_detection_jobs_owner_id_users"), type_="foreignkey")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("summary_json")
        batch_op.drop_column("annotated_storage_key")
        batch_op.drop_column("video_duration_ms")
        batch_op.drop_column("total_frames_sampled")
        batch_op.drop_column("max_frames")
        batch_op.drop_column("frame_sample_interval_ms")
        batch_op.drop_column("device_used")
        batch_op.drop_column("model_checksum")
        batch_op.drop_column("media_type")
        batch_op.drop_column("progress_percent")
        batch_op.drop_column("model_id")
        batch_op.drop_column("detection_mode")
        batch_op.drop_column("mission_id")
        batch_op.drop_column("field_id")
        batch_op.drop_column("owner_id")

    op.drop_table("registered_datasets")
