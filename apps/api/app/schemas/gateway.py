"""Pydantic v2 schemas for Phase 4 Field Edge Gateway enrollment, heartbeat, relay, and snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeploymentMode = Literal["local_dev", "remote_cloud"]
GatewayStatus = Literal["enrolled", "active", "revoked"]


class GatewayEnrollRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    gateway_identifier: str = Field(
        min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    device_id: uuid.UUID | None = None
    deployment_mode: DeploymentMode = "local_dev"


class GatewayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    name: str
    gateway_identifier: str
    deployment_mode: str
    credential_prefix: str
    credential_version: int
    status: str
    is_live: bool = False
    heartbeat_age_seconds: int | None = None
    camera_reachable: bool
    camera_fps: float | None = None
    dropped_frames: int
    queue_depth: int
    queue_bytes: int
    internet_reachable: bool | None = None
    local_interface: str | None = None
    uplink_interface: str | None = None
    diagnostics_json: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GatewayEnrollResponse(BaseModel):
    gateway: GatewayRead
    # Returned exactly once upon enrollment or credential rotation; never stored in plaintext.
    gateway_token: str


class GatewayHeartbeatRequest(BaseModel):
    camera_reachable: bool
    camera_fps: float | None = Field(default=None, ge=0.0, le=60.0)
    dropped_frames: int = Field(default=0, ge=0)
    queue_depth: int = Field(default=0, ge=0)
    queue_bytes: int = Field(default=0, ge=0)
    internet_reachable: bool | None = None
    deployment_mode: DeploymentMode | None = None
    local_interface: str | None = Field(default=None, max_length=64)
    uplink_interface: str | None = Field(default=None, max_length=64)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class StreamSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gateway_id: uuid.UUID
    device_id: uuid.UUID | None = None
    status: str
    target_fps: float
    max_frame_bytes: int
    frames_relayed: int
    expires_at: datetime
    stopped_at: datetime | None = None
    last_frame_at: datetime | None = None
    created_at: datetime


class GatewayHeartbeatResponse(BaseModel):
    gateway_id: uuid.UUID
    server_time: datetime
    heartbeat_ttl_seconds: int
    stream_active: bool
    active_session: StreamSessionRead | None = None


class StreamStartRequest(BaseModel):
    target_fps: float = Field(default=2.0, ge=0.2, le=5.0)
    max_frame_bytes: int = Field(default=524288, ge=32768, le=2 * 1024 * 1024)
    duration_seconds: int = Field(default=300, ge=30, le=3600)


class GatewayDiagnosticsResponse(BaseModel):
    gateway: GatewayRead
    active_session: StreamSessionRead | None = None
    heartbeat_ttl_seconds: int
    network_guidance: str
    esp32_ap_ssid: str
    esp32_local_url: str
    esp32_stream_url: str
    direct_cloud_probe_allowed: bool


class SnapshotAnalyzeRequest(BaseModel):
    model_id: str = Field(default="yolov8n-coco-general", min_length=2, max_length=80)
    confidence_threshold: float = Field(default=0.35, ge=0.05, le=0.95)


class LocalCaptureAnalyzeRequest(BaseModel):
    model_id: str = Field(default="yolov8n-coco-general", min_length=2, max_length=80)
    confidence_threshold: float = Field(default=0.25, ge=0.05, le=0.95)


class LatestGatewayDetectionItem(BaseModel):
    label: str
    confidence: float


class LatestGatewayDetectionResponse(BaseModel):
    has_result: bool
    job_id: uuid.UUID | None = None
    status: str | None = None
    model_id: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    age_seconds: float | None = None
    camera_reachable: bool
    ai_inference_enabled: bool
    detections: list[LatestGatewayDetectionItem] = Field(default_factory=list)
