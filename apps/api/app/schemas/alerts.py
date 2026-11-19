"""Phase 5 Alert Rules, Operational Alerts & Notification Center Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AlertSeverity = Literal["info", "warning", "critical"]
AlertTriggerType = Literal[
    "yolo_class_detected",
    "confidence_threshold_reached",
    "human_confirmed_detection",
    "ai_analysis_failed",
    "gateway_offline_ttl",
    "mission_status_changed",
]
AlertStatus = Literal["open", "acknowledged", "resolved"]


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    enabled: bool = True
    severity: AlertSeverity = "warning"
    trigger_type: AlertTriggerType
    target_classes: list[str] = Field(default_factory=list)
    min_confidence: float | None = Field(default=None, ge=0.05, le=0.99)
    target_mission_statuses: list[str] = Field(default_factory=list)
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    cooldown_minutes: int = Field(default=15, ge=0, le=10080)

    @field_validator("target_classes", mode="before")
    @classmethod
    def normalize_classes(cls, value: Any) -> list[str]:
        if not value:
            return []
        return [str(item).strip().lower() for item in value if str(item).strip()]


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None
    severity: AlertSeverity | None = None
    target_classes: list[str] | None = None
    min_confidence: float | None = Field(default=None, ge=0.05, le=0.99)
    target_mission_statuses: list[str] | None = None
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)


class AlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    enabled: bool
    severity: str
    trigger_type: str
    target_classes: list[str] = Field(default_factory=list)
    min_confidence: float | None = None
    target_mission_statuses: list[str] = Field(default_factory=list)
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    cooldown_minutes: int
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertResolveRequest(BaseModel):
    resolution_notes: str | None = Field(default=None, max_length=1000)


class AlertPhase5Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    gateway_id: uuid.UUID | None = None
    detection_job_id: uuid.UUID | None = None
    severity: str
    category: str
    title: str
    message: str
    status: str
    dedupe_key: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    acknowledged_by: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class GatewayEvaluationResponse(BaseModel):
    checked_gateways: int
    offline_detected: int
    alerts_created: int


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    alert_id: uuid.UUID | None = None
    severity: str
    title: str
    message: str
    link_path: str | None = None
    is_read: bool
    read_at: datetime | None = None
    channel: str
    delivery_status: str
    created_at: datetime
    updated_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationPreferenceRead(BaseModel):
    in_app_enabled: bool
    email_enabled: bool
    email_address: str | None = None
    min_severity: str
    muted_trigger_types: list[str] = Field(default_factory=list)
    email_available: bool
    email_status_reason: str


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    email_address: str | None = Field(default=None, max_length=255)
    min_severity: AlertSeverity | None = None
    muted_trigger_types: list[str] | None = None
