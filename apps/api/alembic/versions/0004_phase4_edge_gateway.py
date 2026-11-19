"""Phase 4 Edge Gateway: edge_gateways and stream_sessions tables.

Revision ID: 0004_phase4_edge_gateway
Revises: 0003_phase3_agrovision_ai_engine
Create Date: 2026-11-19 17:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID, JSONVariant

revision: str = "0004_phase4_edge_gateway"
down_revision: str | None = "0003_phase3_agrovision_ai_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_gateways",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("gateway_identifier", sa.String(length=100), nullable=False),
        sa.Column(
            "deployment_mode", sa.String(length=32), nullable=False, server_default="local_dev"
        ),
        sa.Column("credential_prefix", sa.String(length=24), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="enrolled"),
        sa.Column("camera_reachable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("camera_fps", sa.Float(), nullable=True),
        sa.Column("dropped_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("internet_reachable", sa.Boolean(), nullable=True),
        sa.Column("local_interface", sa.String(length=64), nullable=True),
        sa.Column("uplink_interface", sa.String(length=64), nullable=True),
        sa.Column("diagnostics_json", JSONVariant, nullable=False, server_default="{}"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_edge_gateways_device_id_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_edge_gateways_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_edge_gateways")),
    )
    op.create_index(op.f("ix_edge_gateways_owner_id"), "edge_gateways", ["owner_id"], unique=False)
    op.create_index(op.f("ix_edge_gateways_device_id"), "edge_gateways", ["device_id"], unique=False)
    op.create_index(
        op.f("ix_edge_gateways_gateway_identifier"),
        "edge_gateways",
        ["gateway_identifier"],
        unique=True,
    )
    op.create_index(
        op.f("ix_edge_gateways_credential_hash"),
        "edge_gateways",
        ["credential_hash"],
        unique=True,
    )
    op.create_index(op.f("ix_edge_gateways_status"), "edge_gateways", ["status"], unique=False)
    op.create_index(
        op.f("ix_edge_gateways_last_heartbeat_at"),
        "edge_gateways",
        ["last_heartbeat_at"],
        unique=False,
    )

    op.create_table(
        "stream_sessions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("gateway_id", GUID(), nullable=False),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("target_fps", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("max_frame_bytes", sa.Integer(), nullable=False, server_default="524288"),
        sa.Column("frames_relayed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_stream_sessions_device_id_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_id"],
            ["edge_gateways.id"],
            name=op.f("fk_stream_sessions_gateway_id_edge_gateways"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_stream_sessions_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_sessions")),
    )
    op.create_index(
        op.f("ix_stream_sessions_gateway_id"), "stream_sessions", ["gateway_id"], unique=False
    )
    op.create_index(
        op.f("ix_stream_sessions_device_id"), "stream_sessions", ["device_id"], unique=False
    )
    op.create_index(
        op.f("ix_stream_sessions_owner_id"), "stream_sessions", ["owner_id"], unique=False
    )
    op.create_index(op.f("ix_stream_sessions_status"), "stream_sessions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("stream_sessions")
    op.drop_table("edge_gateways")
