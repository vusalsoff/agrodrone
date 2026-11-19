"""Phase 5 Smart Analytics & Map Analytics service backed by real persisted records."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    DetectionItem,
    DetectionJob,
    Device,
    EdgeGateway,
    Field,
    GatewayConnectivityEvent,
    MediaAsset,
    Mission,
    User,
)
from app.schemas.analytics import (
    AlertSeveritySummaryItem,
    AnalyticsDetectionsSummary,
    AnalyticsJobsSummary,
    AnalyticsOverviewResponse,
    ClassDistributionItem,
    ConfidenceBucketItem,
    ConnectivityEventItem,
    DetectionTrendPoint,
    DeviceConnectivitySummary,
    FieldAnalyticsSummary,
    MapAnalyticsResponse,
    MapFieldSummary,
    MissionAnalyticsSummary,
    VerifiedMapDetectionPoint,
)

METHODOLOGY_NOTE = (
    "Raw detection instances reflect individual image/frame bounding boxes; unique job-class "
    "occurrences deduplicate repeated class detections across sampled video frames within the same "
    "job. Detection counts are not unique animal/object counts and do not represent validated "
    "agricultural infestation severity."
)

CONFIDENCE_BUCKETS: list[tuple[str, float, float]] = [
    ("0.00 - 0.25", 0.0, 0.25),
    ("0.25 - 0.50", 0.25, 0.50),
    ("0.50 - 0.75", 0.50, 0.75),
    ("0.75 - 0.90", 0.75, 0.90),
    ("0.90 - 1.00", 0.90, 1.01),
]


def parse_date_bounds(
    date_from: str | None, date_to: str | None
) -> tuple[datetime | None, datetime | None]:
    """Parse optional YYYY-MM-DD or ISO datetime bounds into UTC datetimes."""
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    if date_from:
        raw = date_from.strip()
        if len(raw) == 10:
            start_dt = datetime.combine(datetime.fromisoformat(raw).date(), time.min, tzinfo=UTC)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            start_dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    if date_to:
        raw = date_to.strip()
        if len(raw) == 10:
            end_dt = datetime.combine(
                datetime.fromisoformat(raw).date(), time.max, tzinfo=UTC
            ) + timedelta(microseconds=1)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            end_dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    return start_dt, end_dt


def _is_admin(user: User) -> bool:
    return user.role == "admin"


def get_analytics_overview(
    db: Session,
    user: User,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    field_id: uuid.UUID | None = None,
    mission_id: uuid.UUID | None = None,
) -> AnalyticsOverviewResponse:
    """Compute real database-backed analytics scoped to the requesting user (or all for admin)."""
    start_dt, end_dt = parse_date_bounds(date_from, date_to)
    admin = _is_admin(user)

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

    jobs = list(db.scalars(job_stmt.order_by(DetectionJob.created_at.asc())).all())
    job_ids = [j.id for j in jobs]

    total_jobs = len(jobs)
    completed_jobs = sum(1 for j in jobs if j.status == "completed")
    failed_jobs = sum(1 for j in jobs if j.status == "failed")
    active_or_queued = sum(1 for j in jobs if j.status in {"queued", "processing"})
    cancelled_jobs = sum(1 for j in jobs if j.status == "cancelled")
    durations = [j.inference_ms for j in jobs if j.status == "completed" and j.inference_ms is not None]
    avg_inference_ms = round(sum(durations) / len(durations), 1) if durations else None

    items: list[DetectionItem] = []
    if job_ids:
        items = list(
            db.scalars(
                select(DetectionItem).where(DetectionItem.job_id.in_(job_ids))
            ).all()
        )

    job_by_id = {j.id: j for j in jobs}
    unique_job_label_pairs: set[tuple[uuid.UUID, str]] = set()
    confirmed_count = 0
    rejected_count = 0
    uncertain_count = 0
    unreviewed_count = 0

    class_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "raw_count": 0,
            "job_ids": set(),
            "confirmed_count": 0,
            "conf_sum": 0.0,
        }
    )
    bucket_counts = [0 for _ in CONFIDENCE_BUCKETS]

    for item in items:
        unique_job_label_pairs.add((item.job_id, item.label))
        if item.review_status == "confirmed":
            confirmed_count += 1
        elif item.review_status == "rejected":
            rejected_count += 1
        elif item.review_status == "uncertain":
            uncertain_count += 1
        else:
            unreviewed_count += 1

        entry = class_stats[item.label]
        entry["raw_count"] += 1
        entry["job_ids"].add(item.job_id)
        if item.review_status == "confirmed":
            entry["confirmed_count"] += 1
        entry["conf_sum"] += float(item.confidence)

        for idx, (_, low, high) in enumerate(CONFIDENCE_BUCKETS):
            if low <= float(item.confidence) < high:
                bucket_counts[idx] += 1
                break

    class_distribution = [
        ClassDistributionItem(
            label=label,
            raw_count=data["raw_count"],
            unique_job_count=len(data["job_ids"]),
            confirmed_count=data["confirmed_count"],
            avg_confidence=round(data["conf_sum"] / data["raw_count"], 4),
        )
        for label, data in sorted(
            class_stats.items(), key=lambda pair: (-pair[1]["raw_count"], pair[0])
        )
    ]

    confidence_distribution = [
        ConfidenceBucketItem(
            bucket_label=label,
            min_score=low,
            max_score=min(high, 1.0),
            count=bucket_counts[idx],
        )
        for idx, (label, low, high) in enumerate(CONFIDENCE_BUCKETS)
    ]

    # Daily detection trends
    trend_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "jobs_completed": 0,
            "jobs_failed": 0,
            "raw_detections": 0,
            "job_label_pairs": set(),
            "confirmed_detections": 0,
        }
    )
    for j in jobs:
        day_key = j.created_at.astimezone(UTC).date().isoformat()
        if j.status == "completed":
            trend_map[day_key]["jobs_completed"] += 1
        elif j.status == "failed":
            trend_map[day_key]["jobs_failed"] += 1

    for item in items:
        job = job_by_id.get(item.job_id)
        if job is None:
            continue
        day_key = job.created_at.astimezone(UTC).date().isoformat()
        trend_map[day_key]["raw_detections"] += 1
        trend_map[day_key]["job_label_pairs"].add((item.job_id, item.label))
        if item.review_status == "confirmed":
            trend_map[day_key]["confirmed_detections"] += 1

    detection_trends = [
        DetectionTrendPoint(
            date=day_key,
            jobs_completed=data["jobs_completed"],
            jobs_failed=data["jobs_failed"],
            raw_detections=data["raw_detections"],
            unique_job_class_occurrences=len(data["job_label_pairs"]),
            confirmed_detections=data["confirmed_detections"],
        )
        for day_key, data in sorted(trend_map.items())
    ]

    # Field summaries
    field_stmt = select(Field)
    if not admin:
        field_stmt = field_stmt.where(Field.owner_id == user.id)
    if field_id is not None:
        field_stmt = field_stmt.where(Field.id == field_id)
    fields = list(db.scalars(field_stmt.order_by(Field.name.asc())).all())
    field_name_by_id = {f.id: f.name for f in fields}

    mission_stmt = select(Mission)
    if not admin:
        mission_stmt = mission_stmt.where(Mission.owner_id == user.id)
    if field_id is not None:
        mission_stmt = mission_stmt.where(Mission.field_id == field_id)
    if mission_id is not None:
        mission_stmt = mission_stmt.where(Mission.id == mission_id)
    if start_dt is not None:
        mission_stmt = mission_stmt.where(Mission.created_at >= start_dt)
    if end_dt is not None:
        mission_stmt = mission_stmt.where(Mission.created_at <= end_dt)
    missions = list(db.scalars(mission_stmt.order_by(Mission.updated_at.desc())).all())

    items_by_job: dict[uuid.UUID, list[DetectionItem]] = defaultdict(list)
    for item in items:
        items_by_job[item.job_id].append(item)

    field_summaries: list[FieldAnalyticsSummary] = []
    for f in fields:
        f_jobs = [j for j in jobs if j.field_id == f.id]
        f_items = [it for j in f_jobs for it in items_by_job.get(j.id, [])]
        f_unique = {(it.job_id, it.label) for it in f_items}
        f_missions = [m for m in missions if m.field_id == f.id]
        field_summaries.append(
            FieldAnalyticsSummary(
                field_id=f.id,
                field_name=f.name,
                code=f.code,
                crop_type=f.crop_type,
                area_hectares=f.area_hectares,
                missions_count=len(f_missions),
                jobs_count=len(f_jobs),
                completed_jobs=sum(1 for j in f_jobs if j.status == "completed"),
                raw_detections=len(f_items),
                unique_job_class_occurrences=len(f_unique),
                confirmed_detections=sum(1 for it in f_items if it.review_status == "confirmed"),
            )
        )

    mission_summaries: list[MissionAnalyticsSummary] = []
    for m in missions:
        m_jobs = [j for j in jobs if j.mission_id == m.id]
        m_items = [it for j in m_jobs for it in items_by_job.get(j.id, [])]
        m_unique = {(it.job_id, it.label) for it in m_items}
        mission_summaries.append(
            MissionAnalyticsSummary(
                mission_id=m.id,
                title=m.title,
                status=m.status,
                field_id=m.field_id,
                field_name=field_name_by_id.get(m.field_id) if m.field_id else None,
                jobs_count=len(m_jobs),
                completed_jobs=sum(1 for j in m_jobs if j.status == "completed"),
                raw_detections=len(m_items),
                unique_job_class_occurrences=len(m_unique),
                confirmed_detections=sum(1 for it in m_items if it.review_status == "confirmed"),
                updated_at=m.updated_at,
            )
        )

    # Alert severity distribution
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
    alerts = list(db.scalars(alert_stmt).all())

    sev_counts = {"info": 0, "warning": 0, "critical": 0}
    open_alerts = 0
    acknowledged_alerts = 0
    resolved_alerts = 0
    for a in alerts:
        sev_counts[a.severity] = sev_counts.get(a.severity, 0) + 1
        if a.status == "open":
            open_alerts += 1
        elif a.status == "acknowledged":
            acknowledged_alerts += 1
        elif a.status == "resolved":
            resolved_alerts += 1

    alert_severity_distribution = [
        AlertSeveritySummaryItem(severity=sev, count=sev_counts[sev])
        for sev in ("critical", "warning", "info")
    ]

    # Device & gateway connectivity history where actual events exist
    gw_stmt = select(EdgeGateway)
    if not admin:
        gw_stmt = gw_stmt.where(EdgeGateway.owner_id == user.id)
    gateways = list(db.scalars(gw_stmt.order_by(EdgeGateway.created_at.desc())).all())
    device_ids = [gw.device_id for gw in gateways if gw.device_id is not None]
    device_names: dict[uuid.UUID, str] = {}
    if device_ids:
        for dev in db.scalars(select(Device).where(Device.id.in_(device_ids))).all():
            device_names[dev.id] = dev.name

    device_connectivity: list[DeviceConnectivitySummary] = []
    for gw in gateways:
        ev_stmt = select(GatewayConnectivityEvent).where(
            GatewayConnectivityEvent.gateway_id == gw.id
        )
        if start_dt is not None:
            ev_stmt = ev_stmt.where(GatewayConnectivityEvent.created_at >= start_dt)
        if end_dt is not None:
            ev_stmt = ev_stmt.where(GatewayConnectivityEvent.created_at <= end_dt)
        events = list(
            db.scalars(ev_stmt.order_by(GatewayConnectivityEvent.created_at.desc()).limit(20)).all()
        )
        total_events = (
            db.scalar(
                select(func.count())
                .select_from(GatewayConnectivityEvent)
                .where(GatewayConnectivityEvent.gateway_id == gw.id)
            )
            or 0
        )
        offline_events = (
            db.scalar(
                select(func.count())
                .select_from(GatewayConnectivityEvent)
                .where(
                    GatewayConnectivityEvent.gateway_id == gw.id,
                    GatewayConnectivityEvent.event_type == "offline_ttl_exceeded",
                )
            )
            or 0
        )
        device_connectivity.append(
            DeviceConnectivitySummary(
                gateway_id=gw.id,
                gateway_name=gw.name,
                gateway_identifier=gw.gateway_identifier,
                device_id=gw.device_id,
                device_name=device_names.get(gw.device_id) if gw.device_id else None,
                current_status=gw.status,
                last_heartbeat_at=gw.last_heartbeat_at,
                total_events=total_events,
                offline_events=offline_events,
                recent_events=[
                    ConnectivityEventItem(
                        id=ev.id,
                        event_type=ev.event_type,
                        camera_reachable=ev.camera_reachable,
                        internet_reachable=ev.internet_reachable,
                        camera_fps=ev.camera_fps,
                        dropped_frames=ev.dropped_frames,
                        detail=ev.detail,
                        created_at=ev.created_at,
                    )
                    for ev in events
                ],
            )
        )

    return AnalyticsOverviewResponse(
        generated_at=datetime.now(UTC),
        date_from=date_from,
        date_to=date_to,
        field_id=field_id,
        mission_id=mission_id,
        methodology_note=METHODOLOGY_NOTE,
        jobs_summary=AnalyticsJobsSummary(
            total_jobs=total_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            active_or_queued_jobs=active_or_queued,
            cancelled_jobs=cancelled_jobs,
            avg_inference_ms=avg_inference_ms,
        ),
        detections_summary=AnalyticsDetectionsSummary(
            raw_detection_items=len(items),
            unique_job_class_occurrences=len(unique_job_label_pairs),
            human_confirmed_count=confirmed_count,
            human_rejected_count=rejected_count,
            human_uncertain_count=uncertain_count,
            unreviewed_count=unreviewed_count,
        ),
        class_distribution=class_distribution,
        confidence_distribution=confidence_distribution,
        detection_trends=detection_trends,
        field_summaries=field_summaries,
        mission_summaries=mission_summaries,
        alert_severity_distribution=alert_severity_distribution,
        open_alerts=open_alerts,
        acknowledged_alerts=acknowledged_alerts,
        resolved_alerts=resolved_alerts,
        device_connectivity=device_connectivity,
    )


def get_map_analytics(
    db: Session,
    user: User,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> MapAnalyticsResponse:
    """Return field summaries and verified geotagged media points (never fabricated GPS)."""
    overview = get_analytics_overview(db, user, date_from=date_from, date_to=date_to)
    summary_by_field = {fs.field_id: fs for fs in overview.field_summaries}

    field_stmt = select(Field)
    if not _is_admin(user):
        field_stmt = field_stmt.where(Field.owner_id == user.id)
    fields = list(db.scalars(field_stmt.order_by(Field.name.asc())).all())

    map_fields: list[MapFieldSummary] = []
    for f in fields:
        fs = summary_by_field.get(f.id)
        map_fields.append(
            MapFieldSummary(
                field_id=f.id,
                name=f.name,
                code=f.code,
                crop_type=f.crop_type,
                area_hectares=f.area_hectares,
                centroid_lat=f.centroid_lat,
                centroid_lng=f.centroid_lng,
                boundary_geojson=f.boundary_geojson,
                missions_count=fs.missions_count if fs else 0,
                jobs_count=fs.jobs_count if fs else 0,
                raw_detections=fs.raw_detections if fs else 0,
                unique_job_class_occurrences=fs.unique_job_class_occurrences if fs else 0,
                confirmed_detections=fs.confirmed_detections if fs else 0,
            )
        )

    # Verified geographic detection locations ONLY where actual coordinates exist on MediaAsset
    media_stmt = select(MediaAsset).where(
        MediaAsset.geo_lat.is_not(None),
        MediaAsset.geo_lng.is_not(None),
        MediaAsset.geo_source != "none",
    )
    if not _is_admin(user):
        media_stmt = media_stmt.where(MediaAsset.uploaded_by == user.id)
    geo_assets = list(db.scalars(media_stmt).all())

    verified_points: list[VerifiedMapDetectionPoint] = []
    if geo_assets:
        asset_ids = [m.id for m in geo_assets]
        jobs = list(
            db.scalars(
                select(DetectionJob).where(
                    DetectionJob.media_asset_id.in_(asset_ids),
                    DetectionJob.status == "completed",
                )
            ).all()
        )
        job_ids = [j.id for j in jobs]
        items = (
            list(db.scalars(select(DetectionItem).where(DetectionItem.job_id.in_(job_ids))).all())
            if job_ids
            else []
        )
        items_by_job: dict[uuid.UUID, list[DetectionItem]] = defaultdict(list)
        for it in items:
            items_by_job[it.job_id].append(it)

        jobs_by_asset: dict[uuid.UUID, list[DetectionJob]] = defaultdict(list)
        for j in jobs:
            jobs_by_asset[j.media_asset_id].append(j)

        for asset in geo_assets:
            asset_jobs = jobs_by_asset.get(asset.id, [])
            asset_items = [it for j in asset_jobs for it in items_by_job.get(j.id, [])]
            if not asset_items:
                continue
            verified_points.append(
                VerifiedMapDetectionPoint(
                    media_asset_id=asset.id,
                    original_filename=asset.original_filename,
                    field_id=asset.field_id,
                    mission_id=asset.mission_id,
                    geo_lat=float(asset.geo_lat),  # type: ignore[arg-type]
                    geo_lng=float(asset.geo_lng),  # type: ignore[arg-type]
                    geo_source=asset.geo_source,
                    detection_count=len(asset_items),
                    confirmed_count=sum(1 for it in asset_items if it.review_status == "confirmed"),
                    captured_at=asset.captured_at,
                )
            )

    return MapAnalyticsResponse(
        generated_at=datetime.now(UTC),
        gps_telemetry_available=False,
        gps_honesty_note=(
            "E88 dual-camera drone and ESP32-CAM have no verified GPS telemetry integration. "
            "Detections are never placed at fabricated coordinates inside fields; only media assets "
            "with verified EXIF or operator-recorded coordinates are plotted."
        ),
        fields=map_fields,
        verified_detection_points=verified_points,
    )
