"""Mission / Field Capture Session ORM model with state machine and manual observations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class Mission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "missions"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft | planned | in_progress | completed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Chronological list of manual operator observations (never simulated flight telemetry).
    observations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONVariant, default=list, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )
