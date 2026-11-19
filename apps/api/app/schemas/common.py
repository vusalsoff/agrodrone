"""Shared API schema primitives (pagination and error envelopes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
    timestamp: datetime


class PaginatedResponse[T](BaseModel):
    items: list[T] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
