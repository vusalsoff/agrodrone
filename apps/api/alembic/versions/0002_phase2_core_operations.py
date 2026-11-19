"""Phase 2 core operations: refresh tokens, audit logs, ownership, device identifiers, observations, media metadata.

Revision ID: 0002_phase2_core_operations
Revises: 0001_initial_foundation
Create Date: 2026-11-19 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID, JSONVariant

revision: str = "0002_phase2_core_operations"
down_revision: str | None = "0001_initial_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_family", GUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", GUID(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(
        op.f("ix_refresh_tokens_token_family"), "refresh_tokens", ["token_family"], unique=False
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("actor_id", GUID(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=48), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_type"), "audit_logs", ["resource_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_id"), "audit_logs", ["resource_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)

    with op.batch_alter_table("fields") as batch_op:
        batch_op.add_column(sa.Column("owner_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("location", sa.String(length=200), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_fields_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_fields_owner_id"), ["owner_id"], unique=False)

    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("owner_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("assigned_field_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("device_identifier", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("connection_config", JSONVariant, nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("last_authenticated_contact_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            op.f("fk_devices_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            op.f("fk_devices_assigned_field_id_fields"),
            "fields",
            ["assigned_field_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_devices_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(
            op.f("ix_devices_assigned_field_id"), ["assigned_field_id"], unique=False
        )
        batch_op.create_index(
            op.f("ix_devices_device_identifier"), ["device_identifier"], unique=True
        )

    with op.batch_alter_table("missions") as batch_op:
        batch_op.add_column(sa.Column("owner_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("observations", JSONVariant, nullable=False, server_default="[]")
        )
        batch_op.create_foreign_key(
            op.f("fk_missions_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_missions_owner_id"), ["owner_id"], unique=False)

    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.add_column(
            sa.Column("media_type", sa.String(length=16), nullable=False, server_default="image")
        )
        batch_op.add_column(
            sa.Column(
                "upload_status", sa.String(length=24), nullable=False, server_default="uploaded"
            )
        )
        batch_op.add_column(sa.Column("safe_filename", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.create_index(op.f("ix_media_assets_uploaded_by"), ["uploaded_by"], unique=False)
        batch_op.create_index(op.f("ix_media_assets_media_type"), ["media_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.drop_index(op.f("ix_media_assets_media_type"))
        batch_op.drop_index(op.f("ix_media_assets_uploaded_by"))
        batch_op.drop_column("notes")
        batch_op.drop_column("safe_filename")
        batch_op.drop_column("upload_status")
        batch_op.drop_column("media_type")

    with op.batch_alter_table("missions") as batch_op:
        batch_op.drop_index(op.f("ix_missions_owner_id"))
        batch_op.drop_constraint(op.f("fk_missions_owner_id_users"), type_="foreignkey")
        batch_op.drop_column("observations")
        batch_op.drop_column("description")
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_index(op.f("ix_devices_device_identifier"))
        batch_op.drop_index(op.f("ix_devices_assigned_field_id"))
        batch_op.drop_index(op.f("ix_devices_owner_id"))
        batch_op.drop_constraint(op.f("fk_devices_assigned_field_id_fields"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_devices_owner_id_users"), type_="foreignkey")
        batch_op.drop_column("last_authenticated_contact_at")
        batch_op.drop_column("connection_config")
        batch_op.drop_column("device_identifier")
        batch_op.drop_column("assigned_field_id")
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("fields") as batch_op:
        batch_op.drop_index(op.f("ix_fields_owner_id"))
        batch_op.drop_constraint(op.f("fk_fields_owner_id_users"), type_="foreignkey")
        batch_op.drop_column("location")
        batch_op.drop_column("description")
        batch_op.drop_column("owner_id")

    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
