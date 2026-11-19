"""System health, operational status, and honest hardware/AI capability schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    database_connected: bool
    database_dialect: str
    database_latency_ms: float | None = None
    timestamp: datetime


class EntityCounts(BaseModel):
    fields: int = Field(ge=0)
    devices: int = Field(ge=0)
    missions: int = Field(ge=0)
    media_assets: int = Field(ge=0)
    detection_jobs: int = Field(ge=0)
    open_alerts: int = Field(ge=0)


class SubsystemStatus(BaseModel):
    id: str
    name: str
    status: Literal["operational", "standby", "unconfigured", "isolated_local", "degraded"]
    summary: str
    target_phase: str


class SystemStatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    phase: str
    database_connected: bool
    database_dialect: str
    database_latency_ms: float | None = None
    storage_backend: str
    ai_inference_enabled: bool
    edge_gateway_enabled: bool
    counts: EntityCounts
    subsystems: list[SubsystemStatus]
    timestamp: datetime


class HardwareDeviceSpec(BaseModel):
    id: str
    name: str
    category: Literal["airframe", "camera_module", "programmer", "power_source"]
    connectivity_mode: Literal["manual_rf", "isolated_ap", "usb_serial_bench", "unmanaged_power"]
    local_ssid: str | None = None
    local_dashboard_url: str | None = None
    local_stream_url: str | None = None
    cloud_directly_reachable: bool
    supported_capabilities: list[str]
    unsupported_capabilities: list[str]


class NetworkBoundaryPolicy(BaseModel):
    esp32_ap_ssid: str
    esp32_dashboard_url: str
    esp32_mjpeg_stream_url: str
    direct_cloud_probe_allowed: bool
    gateway_status: Literal["not_deployed_phase_4", "connected", "offline"]
    explanation: str


class AICapabilityPolicy(BaseModel):
    inference_enabled: bool
    active_model_profile: str
    first_working_workflow: str
    model_honesty_notice: str
    validated_target_classes: list[str]
    requires_custom_training_for: list[str]


class ModuleReadinessItem(BaseModel):
    id: str
    name: str
    route: str
    phase: str
    status: Literal["foundation_active", "schema_ready", "planned"]
    summary: str


class CapabilitiesResponse(BaseModel):
    hardware_baseline: list[HardwareDeviceSpec]
    network_boundary: NetworkBoundaryPolicy
    ai_policy: AICapabilityPolicy
    modules: list[ModuleReadinessItem]
