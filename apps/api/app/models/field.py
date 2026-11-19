"""Agricultural Field / Parcel ORM model with ownership and GeoJSON boundary."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONVariant


class Field(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fields"

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    crop_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    area_hectares: Mapped[float | None] = mapped_column(Float, nullable=True)
    boundary_geojson: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
