"""Uploaded Media Asset ORM model (images and videos) with strict ownership & integrity."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"

    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    media_type: Mapped[str] = mapped_column(String(16), default="image", nullable=False, index=True)
    upload_status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(16), default="local", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    safe_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    geo_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # none | exif | manual_operator | gateway_gps
    geo_source: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
