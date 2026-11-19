"""Hardware Device ORM model (airframes, ESP32-CAM modules, edge gateways)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    device_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    device_identifier: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    hardware_model: Mapped[str] = mapped_column(String(160), nullable=False)
    # isolated_ap | manual_import | edge_gateway
    connectivity_mode: Mapped[str] = mapped_column(
        String(32), default="isolated_ap", nullable=False
    )
    # registered | offline_isolated_ap | maintenance | decommissioned (online ONLY via Phase 4 auth gateway)
    status: Mapped[str] = mapped_column(String(32), default="offline_isolated_ap", nullable=False)
    local_ssid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_endpoint_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connection_config: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_authenticated_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
