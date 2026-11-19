"""Phase 5 Professional Report Preview & Export (PDF, CSV, JSON) endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.audit import record_audit_event
from app.schemas.reports import ReportFormat, ReportPreviewResponse, ReportType
from app.services.reports import build_report_preview, render_report_bytes

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/preview",
    response_model=ReportPreviewResponse,
    summary="Preview structured report metrics, provenance, and limitations",
)
def preview_report(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    report_type: ReportType = Query(default="field_analysis"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    field_id: uuid.UUID | None = Query(default=None),
    mission_id: uuid.UUID | None = Query(default=None),
) -> ReportPreviewResponse:
    return build_report_preview(
        db,
        current_user,
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )


@router.get(
    "/export",
    summary="Export downloadable agricultural intelligence report (PDF, CSV, JSON)",
)
def export_report(
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    report_type: ReportType = Query(default="field_analysis"),
    report_format: ReportFormat = Query(default="pdf", alias="format"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    field_id: uuid.UUID | None = Query(default=None),
    mission_id: uuid.UUID | None = Query(default=None),
) -> Response:
    content, media_type, filename = render_report_bytes(
        db,
        current_user,
        report_type=report_type,
        report_format=report_format,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )
    record_audit_event(
        db,
        action="report.export",
        resource_type="report",
        resource_id=report_type,
        actor=current_user,
        request=request,
        metadata={"format": report_format, "filename": filename},
    )
    db.commit()
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
