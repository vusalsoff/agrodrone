"""Phase 5 Smart Analytics & Map Analytics Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnalyticsJobsSummary(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_or_queued_jobs: int
    cancelled_jobs: int
    avg_inference_ms: float | None = None


class AnalyticsDetectionsSummary(BaseModel):
    raw_detection_items: int
    unique_job_class_occurrences: int
    human_confirmed_count: int
    human_rejected_count: int
    human_uncertain_count: int
    unreviewed_count: int


class ClassDistributionItem(BaseModel):
    label: str
    raw_count: int
    unique_job_count: int
    confirmed_count: int
    avg_confidence: float


class ConfidenceBucketItem(BaseModel):
    bucket_label: str
    min_score: float
    max_score: float
    count: int


class DetectionTrendPoint(BaseModel):
    date: str
    jobs_completed: int
    jobs_failed: int
    raw_detections: int
    unique_job_class_occurrences: int
    confirmed_detections: int


class FieldAnalyticsSummary(BaseModel):
    field_id: uuid.UUID
    field_name: str
    code: str
    crop_type: str | None = None
    area_hectares: float | None = None
    missions_count: int
    jobs_count: int
    completed_jobs: int
    raw_detections: int
    unique_job_class_occurrences: int
    confirmed_detections: int


class MissionAnalyticsSummary(BaseModel):
    mission_id: uuid.UUID
    title: str
    status: str
    field_id: uuid.UUID | None = None
    field_name: str | None = None
    jobs_count: int
    completed_jobs: int
    raw_detections: int
    unique_job_class_occurrences: int
    confirmed_detections: int
    updated_at: datetime


class AlertSeveritySummaryItem(BaseModel):
    severity: str
    count: int


class ConnectivityEventItem(BaseModel):
    id: uuid.UUID
    event_type: str
    camera_reachable: bool
    internet_reachable: bool | None = None
    camera_fps: float | None = None
    dropped_frames: int
    detail: str | None = None
    created_at: datetime


class DeviceConnectivitySummary(BaseModel):
    gateway_id: uuid.UUID
    gateway_name: str
    gateway_identifier: str
    device_id: uuid.UUID | None = None
    device_name: str | None = None
    current_status: str
    last_heartbeat_at: datetime | None = None
    total_events: int
    offline_events: int
    recent_events: list[ConnectivityEventItem] = Field(default_factory=list)


class AnalyticsOverviewResponse(BaseModel):
    generated_at: datetime
    date_from: str | None = None
    date_to: str | None = None
    field_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    methodology_note: str
    jobs_summary: AnalyticsJobsSummary
    detections_summary: AnalyticsDetectionsSummary
    class_distribution: list[ClassDistributionItem] = Field(default_factory=list)
    confidence_distribution: list[ConfidenceBucketItem] = Field(default_factory=list)
    detection_trends: list[DetectionTrendPoint] = Field(default_factory=list)
    field_summaries: list[FieldAnalyticsSummary] = Field(default_factory=list)
    mission_summaries: list[MissionAnalyticsSummary] = Field(default_factory=list)
    alert_severity_distribution: list[AlertSeveritySummaryItem] = Field(default_factory=list)
    open_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    device_connectivity: list[DeviceConnectivitySummary] = Field(default_factory=list)


class VerifiedMapDetectionPoint(BaseModel):
    media_asset_id: uuid.UUID
    original_filename: str
    field_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    geo_lat: float
    geo_lng: float
    geo_source: str
    detection_count: int
    confirmed_count: int
    captured_at: datetime | None = None


class MapFieldSummary(BaseModel):
    field_id: uuid.UUID
    name: str
    code: str
    crop_type: str | None = None
    area_hectares: float | None = None
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    boundary_geojson: dict[str, Any] | None = None
    missions_count: int
    jobs_count: int
    raw_detections: int
    unique_job_class_occurrences: int
    confirmed_detections: int


class MapAnalyticsResponse(BaseModel):
    generated_at: datetime
    gps_telemetry_available: bool
    gps_honesty_note: str
    fields: list[MapFieldSummary] = Field(default_factory=list)
    verified_detection_points: list[VerifiedMapDetectionPoint] = Field(default_factory=list)
