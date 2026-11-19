"""Phase 5: Smart analytics indexes, alert rules, notifications, preferences, and gateway connectivity events."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID, JSONVariant

revision = "0005_phase5_analytics_alerts_reports"
down_revision = "0004_phase4_edge_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("trigger_type", sa.String(length=48), nullable=False),
        sa.Column("target_classes", JSONVariant, nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("target_mission_statuses", JSONVariant, nullable=False),
        sa.Column("field_id", GUID(), nullable=True),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["fields.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_owner_id", "alert_rules", ["owner_id"])
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])
    op.create_index("ix_alert_rules_severity", "alert_rules", ["severity"])
    op.create_index("ix_alert_rules_trigger_type", "alert_rules", ["trigger_type"])
    op.create_index("ix_alert_rules_field_id", "alert_rules", ["field_id"])
    op.create_index("ix_alert_rules_device_id", "alert_rules", ["device_id"])

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("owner_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("rule_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("mission_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("gateway_id", GUID(), nullable=True))
        batch_op.add_column(sa.Column("dedupe_key", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("metadata_json", JSONVariant, nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("resolved_by", GUID(), nullable=True))
        batch_op.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("resolution_notes", sa.Text(), nullable=True))
        batch_op.create_foreign_key("fk_alerts_owner_id", "users", ["owner_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_alerts_rule_id", "alert_rules", ["rule_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_alerts_mission_id", "missions", ["mission_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_alerts_gateway_id", "edge_gateways", ["gateway_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_alerts_resolved_by", "users", ["resolved_by"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_alerts_owner_id", ["owner_id"])
        batch_op.create_index("ix_alerts_rule_id", ["rule_id"])
        batch_op.create_index("ix_alerts_mission_id", ["mission_id"])
        batch_op.create_index("ix_alerts_gateway_id", ["gateway_id"])
        batch_op.create_index("ix_alerts_dedupe_key", ["dedupe_key"])
        batch_op.create_index("ix_alerts_owner_status_created", ["owner_id", "status", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("alert_id", GUID(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link_path", sa.String(length=255), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="in_app"),
        sa.Column("delivery_status", sa.String(length=32), nullable=False, server_default="delivered"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_alert_id", "notifications", ["alert_id"])
    op.create_index("ix_notifications_severity", "notifications", ["severity"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_address", sa.String(length=255), nullable=True),
        sa.Column("min_severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("muted_trigger_types", JSONVariant, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    op.create_table(
        "gateway_connectivity_events",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("gateway_id", GUID(), nullable=False),
        sa.Column("device_id", GUID(), nullable=True),
        sa.Column("owner_id", GUID(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("camera_reachable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("internet_reachable", sa.Boolean(), nullable=True),
        sa.Column("camera_fps", sa.Float(), nullable=True),
        sa.Column("dropped_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["gateway_id"], ["edge_gateways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gateway_connectivity_events_gateway_id", "gateway_connectivity_events", ["gateway_id"])
    op.create_index("ix_gateway_connectivity_events_device_id", "gateway_connectivity_events", ["device_id"])
    op.create_index("ix_gateway_connectivity_events_owner_id", "gateway_connectivity_events", ["owner_id"])
    op.create_index("ix_gateway_connectivity_events_event_type", "gateway_connectivity_events", ["event_type"])

    op.create_index("ix_detection_jobs_owner_status_created", "detection_jobs", ["owner_id", "status", "created_at"])
    op.create_index("ix_detection_items_job_label_review", "detection_items", ["job_id", "label", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_detection_items_job_label_review", table_name="detection_items")
    op.drop_index("ix_detection_jobs_owner_status_created", table_name="detection_jobs")

    op.drop_table("gateway_connectivity_events")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_index("ix_alerts_owner_status_created")
        batch_op.drop_index("ix_alerts_dedupe_key")
        batch_op.drop_index("ix_alerts_gateway_id")
        batch_op.drop_index("ix_alerts_mission_id")
        batch_op.drop_index("ix_alerts_rule_id")
        batch_op.drop_index("ix_alerts_owner_id")
        batch_op.drop_constraint("fk_alerts_resolved_by", type_="foreignkey")
        batch_op.drop_constraint("fk_alerts_gateway_id", type_="foreignkey")
        batch_op.drop_constraint("fk_alerts_mission_id", type_="foreignkey")
        batch_op.drop_constraint("fk_alerts_rule_id", type_="foreignkey")
        batch_op.drop_constraint("fk_alerts_owner_id", type_="foreignkey")
        batch_op.drop_column("resolution_notes")
        batch_op.drop_column("resolved_at")
        batch_op.drop_column("resolved_by")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("dedupe_key")
        batch_op.drop_column("gateway_id")
        batch_op.drop_column("mission_id")
        batch_op.drop_column("rule_id")
        batch_op.drop_column("owner_id")

    op.drop_table("alert_rules")
