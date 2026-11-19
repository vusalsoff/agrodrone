"""Phase 5 Professional Reporting service (PDF, CSV with formula-injection protection, JSON)."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, DetectionItem, DetectionJob, User
from app.schemas.reports import ReportFormat, ReportPreviewResponse, ReportType
from app.services.analytics import get_analytics_overview, parse_date_bounds

METHODOLOGICAL_LIMITATIONS = [
    "Baseline YOLOv8n uses COCO general-object classes only; specialized crop diseases, pests, snakes, and hedgehogs are not supported unless a validated domain model is registered.",
    "Detection counts represent individual image/frame bounding boxes (with unique job-class counts provided for video deduplication) and do not represent unique animal counts or infestation severity.",
    "E88 dual-camera drone and ESP32-CAM have no verified GPS telemetry or multispectral NIR sensors; true NDVI and unrecorded GPS coordinates are never fabricated.",
]

REPORT_TITLES: dict[ReportType, str] = {
    "field_analysis": "Field Analysis Report",
    "mission_summary": "Mission Summary Report",
    "ai_detection": "AI Detection Report",
    "device_activity": "Device & Gateway Activity Report",
    "alert_history": "Alert History Report",
}


def sanitize_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection (=, +, -, @, tab, CR) in CSV exports."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def build_report_preview(
    db: Session,
    user: User,
    *,
    report_type: ReportType,
    date_from: str | None = None,
    date_to: str | None = None,
    field_id: uuid.UUID | None = None,
    mission_id: uuid.UUID | None = None,
) -> ReportPreviewResponse:
    """Build a user-scoped, provenance-backed report payload from real persisted records."""
    overview = get_analytics_overview(
        db,
        user,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )
    start_dt, end_dt = parse_date_bounds(date_from, date_to)
    admin = user.role == "admin"

    # Model provenance from matching DetectionJobs
    job_stmt = select(DetectionJob)
    if not admin:
        job_stmt = job_stmt.where(DetectionJob.owner_id == user.id)
    if start_dt is not None:
        job_stmt = job_stmt.where(DetectionJob.created_at >= start_dt)
    if end_dt is not None:
        job_stmt = job_stmt.where(DetectionJob.created_at <= end_dt)
    if field_id is not None:
        job_stmt = job_stmt.where(DetectionJob.field_id == field_id)
    if mission_id is not None:
        job_stmt = job_stmt.where(DetectionJob.mission_id == mission_id)
    jobs = list(db.scalars(job_stmt.order_by(DetectionJob.created_at.desc())).all())

    provenance_map: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for j in jobs:
        key = (j.model_id, j.model_version, j.model_checksum)
        if key not in provenance_map:
            provenance_map[key] = {
                "model_id": j.model_id,
                "model_name": j.model_name,
                "model_version": j.model_version,
                "model_checksum": j.model_checksum,
                "dataset_scope": j.dataset_scope,
                "jobs_count": 0,
            }
        provenance_map[key]["jobs_count"] += 1

    human_review_status = {
        "confirmed": overview.detections_summary.human_confirmed_count,
        "rejected": overview.detections_summary.human_rejected_count,
        "uncertain": overview.detections_summary.human_uncertain_count,
        "unreviewed": overview.detections_summary.unreviewed_count,
    }

    rows: list[dict[str, Any]] = []
    summary_metrics: dict[str, Any] = {}

    if report_type == "field_analysis":
        summary_metrics = {
            "fields_count": len(overview.field_summaries),
            "total_jobs": overview.jobs_summary.total_jobs,
            "raw_detection_items": overview.detections_summary.raw_detection_items,
            "unique_job_class_occurrences": overview.detections_summary.unique_job_class_occurrences,
            "human_confirmed_count": overview.detections_summary.human_confirmed_count,
        }
        rows = [fs.model_dump(mode="json") for fs in overview.field_summaries]

    elif report_type == "mission_summary":
        summary_metrics = {
            "missions_count": len(overview.mission_summaries),
            "completed_missions": sum(
                1 for m in overview.mission_summaries if m.status == "completed"
            ),
            "total_jobs": overview.jobs_summary.total_jobs,
            "human_confirmed_count": overview.detections_summary.human_confirmed_count,
        }
        rows = [ms.model_dump(mode="json") for ms in overview.mission_summaries]

    elif report_type == "ai_detection":
        summary_metrics = {
            "total_jobs": overview.jobs_summary.total_jobs,
            "completed_jobs": overview.jobs_summary.completed_jobs,
            "failed_jobs": overview.jobs_summary.failed_jobs,
            "avg_inference_ms": overview.jobs_summary.avg_inference_ms,
            "raw_detection_items": overview.detections_summary.raw_detection_items,
            "unique_job_class_occurrences": overview.detections_summary.unique_job_class_occurrences,
            "human_confirmed_count": overview.detections_summary.human_confirmed_count,
        }
        job_ids = [j.id for j in jobs]
        items_by_job: dict[uuid.UUID, list[DetectionItem]] = {}
        if job_ids:
            for it in db.scalars(select(DetectionItem).where(DetectionItem.job_id.in_(job_ids))).all():
                items_by_job.setdefault(it.job_id, []).append(it)
        for j in jobs:
            j_items = items_by_job.get(j.id, [])
            rows.append(
                {
                    "job_id": str(j.id),
                    "created_at": j.created_at.isoformat(),
                    "status": j.status,
                    "media_type": j.media_type,
                    "model_id": j.model_id,
                    "model_version": j.model_version,
                    "inference_ms": j.inference_ms,
                    "raw_detections": len(j_items),
                    "unique_classes": len({it.label for it in j_items}),
                    "confirmed_detections": sum(
                        1 for it in j_items if it.review_status == "confirmed"
                    ),
                    "field_id": str(j.field_id) if j.field_id else None,
                    "mission_id": str(j.mission_id) if j.mission_id else None,
                }
            )

    elif report_type == "device_activity":
        summary_metrics = {
            "gateways_count": len(overview.device_connectivity),
            "total_connectivity_events": sum(
                g.total_events for g in overview.device_connectivity
            ),
            "offline_ttl_events": sum(
                g.offline_events for g in overview.device_connectivity
            ),
        }
        for gw in overview.device_connectivity:
            rows.append(
                {
                    "gateway_id": str(gw.gateway_id),
                    "gateway_name": gw.gateway_name,
                    "gateway_identifier": gw.gateway_identifier,
                    "device_name": gw.device_name,
                    "current_status": gw.current_status,
                    "last_heartbeat_at": (
                        gw.last_heartbeat_at.isoformat() if gw.last_heartbeat_at else None
                    ),
                    "total_events": gw.total_events,
                    "offline_events": gw.offline_events,
                }
            )

    elif report_type == "alert_history":
        alert_stmt = select(Alert)
        if not admin:
            alert_stmt = alert_stmt.where(Alert.owner_id == user.id)
        if start_dt is not None:
            alert_stmt = alert_stmt.where(Alert.created_at >= start_dt)
        if end_dt is not None:
            alert_stmt = alert_stmt.where(Alert.created_at <= end_dt)
        if field_id is not None:
            alert_stmt = alert_stmt.where(Alert.field_id == field_id)
        if mission_id is not None:
            alert_stmt = alert_stmt.where(Alert.mission_id == mission_id)
        alerts = list(db.scalars(alert_stmt.order_by(Alert.created_at.desc())).all())
        summary_metrics = {
            "total_alerts": len(alerts),
            "open_alerts": sum(1 for a in alerts if a.status == "open"),
            "acknowledged_alerts": sum(1 for a in alerts if a.status == "acknowledged"),
            "resolved_alerts": sum(1 for a in alerts if a.status == "resolved"),
        }
        rows = [
            {
                "alert_id": str(a.id),
                "created_at": a.created_at.isoformat(),
                "severity": a.severity,
                "category": a.category,
                "status": a.status,
                "title": a.title,
                "message": a.message,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in alerts
        ]

    return ReportPreviewResponse(
        report_type=report_type,
        title=REPORT_TITLES[report_type],
        generated_at=datetime.now(UTC),
        generated_by_email=user.email,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
        summary_metrics=summary_metrics,
        model_provenance=list(provenance_map.values()),
        human_review_status=human_review_status,
        methodological_limitations=METHODOLOGICAL_LIMITATIONS,
        rows=rows,
    )


def render_report_bytes(
    db: Session,
    user: User,
    *,
    report_type: ReportType,
    report_format: ReportFormat,
    date_from: str | None = None,
    date_to: str | None = None,
    field_id: uuid.UUID | None = None,
    mission_id: uuid.UUID | None = None,
) -> tuple[bytes, str, str]:
    """Render report in PDF, CSV, or JSON and return (content_bytes, media_type, filename)."""
    preview = build_report_preview(
        db,
        user,
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )
    overview = get_analytics_overview(
        db,
        user,
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"agrodrone-{report_type}-{stamp}"

    if report_format == "json":
        payload = preview.model_dump(mode="json")
        return (
            json.dumps(payload, indent=2).encode("utf-8"),
            "application/json",
            f"{base_name}.json",
        )

    if report_format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["AgroDrone Report", sanitize_csv_cell(preview.title)])
        writer.writerow(["Generated At (UTC)", sanitize_csv_cell(preview.generated_at.isoformat())])
        writer.writerow(["Generated By", sanitize_csv_cell(preview.generated_by_email)])
        writer.writerow(["Date Range", sanitize_csv_cell(f"{date_from or 'all'} -> {date_to or 'all'}")])
        writer.writerow([])
        if preview.rows:
            headers = list(preview.rows[0].keys())
            writer.writerow([sanitize_csv_cell(h) for h in headers])
            for row in preview.rows:
                writer.writerow([sanitize_csv_cell(row.get(h)) for h in headers])
        else:
            writer.writerow(["Notice", "No matching records found for the selected filters."])
        writer.writerow([])
        writer.writerow(["Methodological Limitations"])
        for note in preview.methodological_limitations:
            writer.writerow([sanitize_csv_cell(note)])
        return (
            buf.getvalue().encode("utf-8-sig"),
            "text/csv; charset=utf-8",
            f"{base_name}.csv",
        )

    # Multi-page PDF via Matplotlib PdfPages
    pdf_buf = io.BytesIO()
    with PdfPages(pdf_buf) as pdf:
        # Page 1: Executive Summary & Provenance
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("#0c1116")
        ax = fig.add_axes([0.06, 0.05, 0.88, 0.90])
        ax.set_facecolor("#0c1116")
        ax.axis("off")

        y = 0.97
        ax.text(0.0, y, "AGRODRONE — AGRICULTURAL INTELLIGENCE REPORT", color="#10b981", fontsize=11, fontweight="bold")
        y -= 0.04
        ax.text(0.0, y, preview.title, color="#f8fafc", fontsize=18, fontweight="bold")
        y -= 0.035
        ax.text(
            0.0,
            y,
            f"Generated: {preview.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  |  User: {preview.generated_by_email}",
            color="#94a3b8",
            fontsize=9,
        )
        y -= 0.025
        ax.text(
            0.0,
            y,
            f"Date Range: {date_from or 'All recorded dates'} to {date_to or 'Present'}  |  Field: {field_id or 'All'}  |  Mission: {mission_id or 'All'}",
            color="#94a3b8",
            fontsize=8.5,
        )

        y -= 0.045
        ax.text(0.0, y, "SUMMARY METRICS (PERSISTED RECORDS)", color="#34d399", fontsize=10, fontweight="bold")
        y -= 0.025
        for k, v in preview.summary_metrics.items():
            ax.text(0.02, y, f"• {k.replace('_', ' ').title()}: {v}", color="#e2e8f0", fontsize=9.5)
            y -= 0.024

        y -= 0.02
        ax.text(0.0, y, "HUMAN REVIEW STATUS", color="#34d399", fontsize=10, fontweight="bold")
        y -= 0.025
        review_line = "  |  ".join(f"{k.title()}: {v}" for k, v in preview.human_review_status.items())
        ax.text(0.02, y, review_line, color="#e2e8f0", fontsize=9.5)

        y -= 0.035
        ax.text(0.0, y, "DETECTION MODEL PROVENANCE", color="#34d399", fontsize=10, fontweight="bold")
        y -= 0.025
        if preview.model_provenance:
            for prov in preview.model_provenance[:5]:
                ax.text(
                    0.02,
                    y,
                    f"• {prov['model_id']} (v{prov['model_version']}, jobs={prov['jobs_count']}) — {prov['dataset_scope']}",
                    color="#e2e8f0",
                    fontsize=8.5,
                )
                y -= 0.024
        else:
            ax.text(0.02, y, "• No AI detection jobs matched the selected filters.", color="#94a3b8", fontsize=9)
            y -= 0.024

        y -= 0.025
        ax.text(0.0, y, "METHODOLOGICAL LIMITATIONS", color="#fbbf24", fontsize=10, fontweight="bold")
        y -= 0.025
        for note in preview.methodological_limitations:
            ax.text(0.02, y, f"• {note}", color="#cbd5e1", fontsize=8, wrap=True)
            y -= 0.042

        pdf.savefig(fig, facecolor=fig.get_facecolor())
        plt.close(fig)

        # Page 2: Real Analytics Charts (or explicit empty state)
        fig, axes = plt.subplots(2, 1, figsize=(8.27, 11.69))
        fig.patch.set_facecolor("#0c1116")
        fig.subplots_adjust(hspace=0.38, top=0.92, bottom=0.08, left=0.12, right=0.94)

        ax1, ax2 = axes
        for ax_item in (ax1, ax2):
            ax_item.set_facecolor("#111827")
            ax_item.tick_params(colors="#cbd5e1", labelsize=8)
            for spine in ax_item.spines.values():
                spine.set_color("#334155")

        if overview.class_distribution:
            top_classes = overview.class_distribution[:10]
            labels = [c.label for c in top_classes]
            raw_vals = [c.raw_count for c in top_classes]
            uniq_vals = [c.unique_job_count for c in top_classes]
            x = range(len(labels))
            ax1.bar([i - 0.18 for i in x], raw_vals, width=0.35, color="#10b981", label="Raw Detections")
            ax1.bar([i + 0.18 for i in x], uniq_vals, width=0.35, color="#38bdf8", label="Unique Job-Class")
            ax1.set_xticks(list(x))
            ax1.set_xticklabels(labels, rotation=25, ha="right")
            ax1.set_title("Detected Class Distribution (Raw vs Deduplicated)", color="#f8fafc", fontsize=11)
            ax1.legend(facecolor="#0f172a", edgecolor="#334155", labelcolor="#e2e8f0", fontsize=8)
        else:
            ax1.text(0.5, 0.5, "No detection class records for selected filters", color="#94a3b8", ha="center", va="center")
            ax1.set_title("Detected Class Distribution", color="#f8fafc", fontsize=11)

        if overview.detection_trends:
            dates = [pt.date for pt in overview.detection_trends]
            raw_t = [pt.raw_detections for pt in overview.detection_trends]
            conf_t = [pt.confirmed_detections for pt in overview.detection_trends]
            ax2.plot(dates, raw_t, marker="o", color="#10b981", label="Raw Detections")
            ax2.plot(dates, conf_t, marker="s", color="#f59e0b", label="Human Confirmed")
            ax2.tick_params(axis="x", rotation=25)
            ax2.set_title("Detection Trends by Date", color="#f8fafc", fontsize=11)
            ax2.legend(facecolor="#0f172a", edgecolor="#334155", labelcolor="#e2e8f0", fontsize=8)
        else:
            ax2.text(0.5, 0.5, "No time-series detection records for selected filters", color="#94a3b8", ha="center", va="center")
            ax2.set_title("Detection Trends by Date", color="#f8fafc", fontsize=11)

        pdf.savefig(fig, facecolor=fig.get_facecolor())
        plt.close(fig)

    return pdf_buf.getvalue(), "application/pdf", f"{base_name}.pdf"
