"""Typed Pydantic v2 schemas for Phase 3 AgroVision model registry, detection jobs, items, review, and datasets."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.domain import MediaAssetRead

DetectionModeType = Literal["general", "wildlife", "pest", "disease"]
JobStatusType = Literal["queued", "processing", "completed", "failed", "cancelled"]
ReviewStatusType = Literal["unreviewed", "confirmed", "rejected", "uncertain"]


class ModelEvaluationSchema(BaseModel):
    dataset_name: str
    dataset_version: str
    train_images: int
    val_images: int
    test_images: int
    precision: float | None = None
    recall: float | None = None
    map50: float | None = None
    map50_95: float | None = None
    notes: str = ""


class ModelRegistryItemSchema(BaseModel):
    model_id: str
    name: str
    version: str
    detection_mode: DetectionModeType
    architecture: str
    license_spdx: str
    dataset_scope: str
    status: Literal["available", "not_available"]
    status_reason: str
    weights_filename: str
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    supported_classes: list[str]
    total_class_count: int
    default_confidence: float
    is_specialized_agricultural: bool
    honesty_disclaimer: str
    evaluation: ModelEvaluationSchema | None = None
    requirements_for_activation: list[str] = Field(default_factory=list)


class DetectionJobCreateRequest(BaseModel):
    media_asset_id: uuid.UUID
    model_id: str = Field(default="yolov8n-coco-general", min_length=2, max_length=80)
    confidence_threshold: float = Field(default=0.35, ge=0.05, le=0.95)
    frame_sample_interval_ms: int = Field(default=1000, ge=200, le=10000)
    max_frames: int = Field(default=20, ge=1, le=120)
    run_async: bool = True


class DetectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    class_id: int | None = None
    label: str
    confidence: float
    original_label: str | None = None
    original_confidence: float | None = None
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    frame_index: int = 0
    timestamp_ms: int | None = None
    annotated_frame_storage_key: str | None = None
    review_status: str
    reviewer_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    reviewer_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class DetectionItemReviewRequest(BaseModel):
    review_status: ReviewStatusType
    reviewer_notes: str | None = Field(default=None, max_length=2000)
    corrected_label: str | None = Field(default=None, max_length=120)


class DetectionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    field_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    media_asset_id: uuid.UUID
    detection_mode: str = "general"
    model_id: str = "yolov8n-coco-general"
    status: str
    progress_percent: int = 0
    media_type: str = "image"
    model_name: str
    model_version: str
    model_checksum: str | None = None
    dataset_scope: str
    device_used: str = "cpu"
    confidence_threshold: float
    frame_sample_interval_ms: int | None = None
    max_frames: int | None = None
    total_frames_sampled: int | None = None
    video_duration_ms: int | None = None
    annotated_storage_key: str | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    inference_ms: int | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DetectionJobDetailRead(DetectionJobRead):
    items: list[DetectionItemRead] = Field(default_factory=list)
    media_asset: MediaAssetRead | None = None


class DatasetMetricsInput(BaseModel):
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    map50: float = Field(ge=0.0, le=1.0)
    map50_95: float | None = Field(default=None, ge=0.0, le=1.0)


class DatasetRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    detection_mode: DetectionModeType
    classes: list[str] = Field(min_length=1, max_length=200)
    train_count: int = Field(ge=1)
    val_count: int = Field(ge=1)
    test_count: int = Field(ge=1)
    metrics: DatasetMetricsInput
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("classes")
    @classmethod
    def clean_classes(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty class name is required.")
        return cleaned


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    name: str
    version: str
    detection_mode: str
    classes_json: list[str]
    train_count: int
    val_count: int
    test_count: int
    metrics_json: dict[str, Any]
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
