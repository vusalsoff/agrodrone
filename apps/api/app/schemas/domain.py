"""Domain entity create, update, transition, and read contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


class FieldCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=200)
    crop_type: str | None = Field(default=None, max_length=100)
    area_hectares: float | None = Field(default=None, gt=0, le=1_000_000)
    boundary_geojson: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name", "code")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()


class FieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code: str | None = Field(
        default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
    )
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=200)
    crop_type: str | None = Field(default=None, max_length=100)
    area_hectares: float | None = Field(default=None, gt=0, le=1_000_000)
    boundary_geojson: dict[str, Any] | None = None
    clear_boundary: bool = False
    notes: str | None = Field(default=None, max_length=4000)


class FieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    name: str
    code: str
    description: str | None = None
    location: str | None = None
    crop_type: str | None = None
    area_hectares: float | None = None
    boundary_geojson: dict[str, Any] | None = None
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

DeviceType = Literal["camera_module", "airframe", "edge_gateway", "sensor_node"]
ConnectivityMode = Literal["isolated_ap", "manual_import", "edge_gateway"]
ManualDeviceStatus = Literal[
    "registered",
    "offline_isolated_ap",
    "awaiting_gateway",
    "maintenance",
    "decommissioned",
]


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    device_type: DeviceType
    device_identifier: str = Field(
        min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    hardware_model: str = Field(min_length=2, max_length=160)
    assigned_field_id: uuid.UUID | None = None
    connectivity_mode: ConnectivityMode = "isolated_ap"
    status: ManualDeviceStatus = "offline_isolated_ap"
    local_ssid: str | None = Field(default=None, max_length=64)
    local_endpoint_url: str | None = Field(default=None, max_length=255)
    connection_config: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    device_type: DeviceType | None = None
    device_identifier: str | None = Field(
        default=None, min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    hardware_model: str | None = Field(default=None, min_length=2, max_length=160)
    assigned_field_id: uuid.UUID | None = None
    unassign_field: bool = False
    connectivity_mode: ConnectivityMode | None = None
    status: ManualDeviceStatus | None = None
    local_ssid: str | None = Field(default=None, max_length=64)
    local_endpoint_url: str | None = Field(default=None, max_length=255)
    connection_config: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    assigned_field_id: uuid.UUID | None = None
    name: str
    device_type: str
    device_identifier: str | None = None
    hardware_model: str
    connectivity_mode: str
    status: str
    local_ssid: str | None = None
    local_endpoint_url: str | None = None
    connection_config: dict[str, Any]
    capabilities: dict[str, Any]
    notes: str | None = None
    last_seen_at: datetime | None = None
    last_authenticated_contact_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------

MissionStatus = Literal["draft", "planned", "in_progress", "completed", "cancelled"]


class MissionObservation(BaseModel):
    id: str
    author_id: str | None = None
    author_name: str
    note: str
    recorded_at: datetime


class MissionObservationCreate(BaseModel):
    note: str = Field(min_length=2, max_length=2000)


class MissionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    status: Literal["draft", "planned"] = "draft"
    operator_notes: str | None = Field(default=None, max_length=4000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MissionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    field_id: uuid.UUID | None = None
    unassign_field: bool = False
    device_id: uuid.UUID | None = None
    unassign_device: bool = False
    operator_notes: str | None = Field(default=None, max_length=4000)
    metadata_json: dict[str, Any] | None = None


class MissionTransitionRequest(BaseModel):
    target_status: MissionStatus
    note: str | None = Field(default=None, max_length=1000)


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    operator_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    status: MissionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    operator_notes: str | None = None
    observations: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Media Assets
# ---------------------------------------------------------------------------


class MediaPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=100)
    byte_size: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")
    field_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_id: uuid.UUID | None = None
    field_id: uuid.UUID | None = None
    uploaded_by: uuid.UUID | None = None
    media_type: str
    upload_status: str
    storage_backend: str
    storage_key: str
    safe_filename: str | None = None
    original_filename: str
    mime_type: str
    byte_size: int
    sha256: str
    width_px: int | None = None
    height_px: int | None = None
    captured_at: datetime | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None
    geo_source: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class MediaPresignResponse(BaseModel):
    asset: MediaAssetRead
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in_seconds: int


class MediaDownloadUrlResponse(BaseModel):
    media_id: uuid.UUID
    storage_backend: str
    url: str
    expires_in_seconds: int | None = None
    filename: str


# ---------------------------------------------------------------------------
# Detections & Alerts (Phase 3 / Phase 5 contracts preserved)
# ---------------------------------------------------------------------------


class DetectionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_asset_id: uuid.UUID
    status: str
    model_name: str
    model_version: str
    dataset_scope: str
    confidence_threshold: float
    inference_ms: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    detection_job_id: uuid.UUID | None = None
    severity: str
    category: str
    title: str
    message: str
    status: str
    acknowledged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
