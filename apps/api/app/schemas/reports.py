"""Phase 5 Professional Reporting Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReportType = Literal[
    "field_analysis",
    "mission_summary",
    "ai_detection",
    "device_activity",
    "alert_history",
]
ReportFormat = Literal["pdf", "csv", "json"]


class ReportPreviewResponse(BaseModel):
    report_type: ReportType
    title: str
    generated_at: datetime
    generated_by_email: str
    date_from: str | None = None
    date_to: str | None = None
    field_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
    model_provenance: list[dict[str, Any]] = Field(default_factory=list)
    human_review_status: dict[str, int] = Field(default_factory=dict)
    methodological_limitations: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
