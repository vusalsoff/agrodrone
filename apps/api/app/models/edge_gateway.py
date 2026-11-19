"""Edge Gateway and bounded Stream Session ORM models for Phase 4 ESP32-CAM bridging."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class EdgeGateway(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "edge_gateways"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    gateway_identifier: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    # local_dev | remote_cloud
    deployment_mode: Mapped[str] = mapped_column(
        String(32), default="local_dev", nullable=False
    )
    credential_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    credential_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    credential_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # enrolled | active | revoked
    status: Mapped[str] = mapped_column(
        String(24), default="enrolled", nullable=False, index=True
    )
    camera_reachable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    camera_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropped_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queue_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queue_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    internet_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    local_interface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uplink_interface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnostics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StreamSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stream_sessions"

    gateway_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("edge_gateways.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # active | stopped | expired
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    target_fps: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    max_frame_bytes: Mapped[int] = mapped_column(Integer, default=524288, nullable=False)
    frames_relayed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GatewayConnectivityEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "gateway_connectivity_events"

    gateway_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("edge_gateways.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # enrolled | heartbeat_online | offline_ttl_exceeded | revoked
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    camera_reachable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    internet_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    camera_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropped_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
