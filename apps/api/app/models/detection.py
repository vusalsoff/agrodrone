"""AI Detection Job, Detection Item, and Registered Dataset ORM models with full provenance & human review."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class DetectionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "detection_jobs"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # general | wildlife | pest | disease
    detection_mode: Mapped[str] = mapped_column(
        String(48), default="general", nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(
        String(80), default="yolov8n-coco-general", nullable=False, index=True
    )
    # queued | processing | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), default="image", nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Explicit provenance so baseline weights are never mislabeled as custom agricultural models.
    dataset_scope: Mapped[str] = mapped_column(String(180), nullable=False)
    device_used: Mapped[str] = mapped_column(String(32), default="cpu", nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.35, nullable=False)
    frame_sample_interval_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_frames_sampled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annotated_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    inference_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DetectionItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "detection_items"

    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("detection_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Original machine prediction preserved separately from human review decisions.
    original_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x2: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y2: Mapped[float] = mapped_column(Float, nullable=False)
    frame_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timestamp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annotated_frame_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # unreviewed | confirmed | rejected | uncertain
    review_status: Mapped[str] = mapped_column(
        String(32), default="unreviewed", nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RegisteredDataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registered_datasets"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    # general | wildlife | pest | disease
    detection_mode: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    classes_json: Mapped[list[str]] = mapped_column(JSONVariant, default=list, nullable=False)
    train_count: Mapped[int] = mapped_column(Integer, nullable=False)
    val_count: Mapped[int] = mapped_column(Integer, nullable=False)
    test_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
