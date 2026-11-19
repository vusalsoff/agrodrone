"""Operational Alerts, Configurable Alert Rules, Notifications & Preferences ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alert_rules"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # info | warning | critical
    severity: Mapped[str] = mapped_column(String(16), default="warning", nullable=False, index=True)
    # yolo_class_detected | confidence_threshold_reached | human_confirmed_detection |
    # ai_analysis_failed | gateway_offline_ttl | mission_status_changed
    trigger_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    target_classes: Mapped[list[str]] = mapped_column(JSONVariant, default=list, nullable=False)
    min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_mission_statuses: Mapped[list[str]] = mapped_column(
        JSONVariant, default=list, nullable=False
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_owner_status_created", "owner_id", "status", "created_at"),
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("edge_gateways.id", ondelete="SET NULL"), nullable=True, index=True
    )
    detection_job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("detection_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # info | warning | critical
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # open | acknowledged | resolved
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="in_app", nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), default="delivered", nullable=False)


class NotificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    muted_trigger_types: Mapped[list[str]] = mapped_column(
        JSONVariant, default=list, nullable=False
    )
