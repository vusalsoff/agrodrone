"""Phase 5 Alert Rule Engine, Deduplication, Cooldowns, Gateway TTL Evaluation & Notifications."""

from __future__ import annotations

import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.models import (
    Alert,
    AlertRule,
    DetectionItem,
    DetectionJob,
    EdgeGateway,
    GatewayConnectivityEvent,
    Mission,
    Notification,
    NotificationPreference,
)
from app.services.vision import GENERAL_MODEL_ID, get_model_catalog

logger = get_logger(__name__)

SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def get_supported_yolo_classes() -> list[str]:
    """Return the exact classes supported by the active baseline YOLO model."""
    for entry in get_model_catalog():
        if entry.model_id == GENERAL_MODEL_ID and entry.status == "available":
            return [c.lower() for c in entry.supported_classes]
    return []


def validate_rule_configuration(
    trigger_type: str,
    target_classes: list[str],
    min_confidence: float | None,
) -> None:
    """Reject unsupported specialized classes or invalid rule thresholds."""
    if trigger_type == "yolo_class_detected":
        if not target_classes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="yolo_class_detected rules require at least one supported YOLO target class.",
            )
        supported = set(get_supported_yolo_classes())
        if not supported:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Baseline YOLOv8n model weights are not currently available to validate classes.",
            )
        unsupported = [cls for cls in target_classes if cls.lower() not in supported]
        if unsupported:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Unsupported target classes {unsupported}. Only validated YOLOv8n COCO classes "
                    "are permitted; specialized pest, snake, hedgehog, or crop disease models are not available."
                ),
            )
    if trigger_type == "confidence_threshold_reached" and min_confidence is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confidence_threshold_reached rules require min_confidence.",
        )


def get_or_create_notification_preferences(
    db: Session, user_id: uuid.UUID
) -> NotificationPreference:
    pref = db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            in_app_enabled=True,
            email_enabled=False,
            min_severity="info",
            muted_trigger_types=[],
        )
        db.add(pref)
        db.flush()
    return pref


def _maybe_send_smtp_email(
    settings: Settings, to_email: str, title: str, message: str
) -> None:
    """Send real SMTP email only when SMTP is configured; never simulate delivery."""
    if not settings.smtp_configured:
        return
    msg = EmailMessage()
    msg["Subject"] = f"[AgroDrone Alert] {title}"
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg.set_content(message)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(msg)


def _dispatch_notification(
    db: Session,
    settings: Settings,
    *,
    user_id: uuid.UUID | None,
    alert: Alert,
    trigger_type: str,
    link_path: str,
) -> None:
    if user_id is None:
        return
    pref = get_or_create_notification_preferences(db, user_id)
    if trigger_type in (pref.muted_trigger_types or []):
        return
    if SEVERITY_RANK.get(alert.severity, 1) < SEVERITY_RANK.get(pref.min_severity, 1):
        return

    if pref.in_app_enabled:
        notif = Notification(
            user_id=user_id,
            alert_id=alert.id,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            link_path=link_path,
            is_read=False,
            channel="in_app",
            delivery_status="delivered",
        )
        db.add(notif)

    if pref.email_enabled and pref.email_address and settings.smtp_configured:
        try:
            _maybe_send_smtp_email(settings, pref.email_address, alert.title, alert.message)
        except Exception as exc:
            logger.warning("alert_smtp_delivery_failed", alert_id=str(alert.id), error=str(exc))


def _create_alert_if_not_deduped(
    db: Session,
    settings: Settings,
    *,
    rule: AlertRule | None,
    owner_id: uuid.UUID | None,
    severity: str,
    category: str,
    title: str,
    message: str,
    dedupe_key: str,
    link_path: str,
    field_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    mission_id: uuid.UUID | None = None,
    gateway_id: uuid.UUID | None = None,
    detection_job_id: uuid.UUID | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> Alert | None:
    now = datetime.now(UTC)

    # Deduplicate against active (open or acknowledged) alerts with same dedupe_key
    existing = db.scalar(
        select(Alert).where(
            Alert.dedupe_key == dedupe_key,
            Alert.status.in_(["open", "acknowledged"]),
        )
    )
    if existing is not None:
        return None

    # Enforce rule cooldown
    if rule is not None and rule.cooldown_minutes > 0 and rule.last_triggered_at is not None:
        last_at = _as_utc(rule.last_triggered_at)
        if last_at is not None and (now - last_at) < timedelta(minutes=rule.cooldown_minutes):
            return None

    alert = Alert(
        owner_id=owner_id,
        rule_id=rule.id if rule else None,
        field_id=field_id,
        device_id=device_id,
        mission_id=mission_id,
        gateway_id=gateway_id,
        detection_job_id=detection_job_id,
        severity=severity,
        category=category,
        title=title[:200],
        message=message,
        status="open",
        dedupe_key=dedupe_key[:160],
        metadata_json=metadata_json or {},
    )
    db.add(alert)
    if rule is not None:
        rule.last_triggered_at = now
    db.flush()

    _dispatch_notification(
        db,
        settings,
        user_id=owner_id,
        alert=alert,
        trigger_type=rule.trigger_type if rule else category,
        link_path=link_path,
    )
    return alert


def evaluate_detection_job_event(
    db: Session, settings: Settings, job_id: uuid.UUID
) -> list[Alert]:
    """Evaluate enabled alert rules when a DetectionJob completes or fails."""
    job = db.get(DetectionJob, job_id)
    if job is None or job.owner_id is None:
        return []

    rules = list(
        db.scalars(
            select(AlertRule).where(
                AlertRule.owner_id == job.owner_id,
                AlertRule.enabled.is_(True),
                AlertRule.trigger_type.in_(
                    ["yolo_class_detected", "confidence_threshold_reached", "ai_analysis_failed"]
                ),
            )
        ).all()
    )
    if not rules:
        return []

    items = list(db.scalars(select(DetectionItem).where(DetectionItem.job_id == job.id)).all())
    created: list[Alert] = []

    for rule in rules:
        if rule.field_id is not None and rule.field_id != job.field_id:
            continue

        if rule.trigger_type == "ai_analysis_failed" and job.status == "failed":
            alert = _create_alert_if_not_deduped(
                db,
                settings,
                rule=rule,
                owner_id=job.owner_id,
                severity=rule.severity,
                category="ai_analysis_failed",
                title=f"AI analysis failed ({job.model_id})",
                message=f"Detection job {job.id} failed: {job.error_message or 'Unknown error'}.",
                dedupe_key=f"rule:{rule.id}:job:{job.id}:failed",
                link_path=f"/history/{job.id}",
                field_id=job.field_id,
                mission_id=job.mission_id,
                detection_job_id=job.id,
                metadata_json={"model_id": job.model_id, "status": job.status},
            )
            if alert:
                created.append(alert)
            continue

        if job.status != "completed" or not items:
            continue

        if rule.trigger_type == "yolo_class_detected":
            targets = {c.lower() for c in (rule.target_classes or [])}
            matched = [
                it
                for it in items
                if it.label.lower() in targets
                and (rule.min_confidence is None or it.confidence >= rule.min_confidence)
            ]
            if matched:
                labels = sorted({it.label for it in matched})
                max_conf = max(it.confidence for it in matched)
                alert = _create_alert_if_not_deduped(
                    db,
                    settings,
                    rule=rule,
                    owner_id=job.owner_id,
                    severity=rule.severity,
                    category="yolo_class_detected",
                    title=f"Detected {', '.join(labels)} ({len(matched)} match{'es' if len(matched) != 1 else ''})",
                    message=(
                        f"Rule '{rule.name}' matched {', '.join(labels)} with peak confidence "
                        f"{max_conf:.2f} in detection job {job.id} using {job.model_id}."
                    ),
                    dedupe_key=f"rule:{rule.id}:job:{job.id}:class",
                    link_path=f"/history/{job.id}",
                    field_id=job.field_id,
                    mission_id=job.mission_id,
                    detection_job_id=job.id,
                    metadata_json={
                        "matched_classes": labels,
                        "match_count": len(matched),
                        "max_confidence": round(max_conf, 4),
                        "model_id": job.model_id,
                    },
                )
                if alert:
                    created.append(alert)

        elif rule.trigger_type == "confidence_threshold_reached" and rule.min_confidence is not None:
            matched = [it for it in items if it.confidence >= rule.min_confidence]
            if matched:
                max_conf = max(it.confidence for it in matched)
                alert = _create_alert_if_not_deduped(
                    db,
                    settings,
                    rule=rule,
                    owner_id=job.owner_id,
                    severity=rule.severity,
                    category="confidence_threshold_reached",
                    title=f"High-confidence detection ({max_conf:.2f})",
                    message=(
                        f"Rule '{rule.name}' triggered on {len(matched)} detection(s) >= "
                        f"{rule.min_confidence:.2f} confidence in job {job.id}."
                    ),
                    dedupe_key=f"rule:{rule.id}:job:{job.id}:conf",
                    link_path=f"/history/{job.id}",
                    field_id=job.field_id,
                    mission_id=job.mission_id,
                    detection_job_id=job.id,
                    metadata_json={
                        "min_confidence": rule.min_confidence,
                        "max_confidence": round(max_conf, 4),
                        "match_count": len(matched),
                    },
                )
                if alert:
                    created.append(alert)

    return created


def evaluate_human_confirmed_event(
    db: Session, settings: Settings, item_id: uuid.UUID
) -> list[Alert]:
    """Evaluate human_confirmed_detection rules when a DetectionItem is confirmed."""
    item = db.get(DetectionItem, item_id)
    if item is None or item.review_status != "confirmed":
        return []
    job = db.get(DetectionJob, item.job_id)
    if job is None or job.owner_id is None:
        return []

    rules = list(
        db.scalars(
            select(AlertRule).where(
                AlertRule.owner_id == job.owner_id,
                AlertRule.enabled.is_(True),
                AlertRule.trigger_type == "human_confirmed_detection",
            )
        ).all()
    )
    created: list[Alert] = []
    for rule in rules:
        if rule.field_id is not None and rule.field_id != job.field_id:
            continue
        if rule.target_classes and item.label.lower() not in {
            c.lower() for c in rule.target_classes
        }:
            continue
        alert = _create_alert_if_not_deduped(
            db,
            settings,
            rule=rule,
            owner_id=job.owner_id,
            severity=rule.severity,
            category="human_confirmed_detection",
            title=f"Human-confirmed detection: {item.label}",
            message=(
                f"Reviewer confirmed '{item.label}' (confidence {item.confidence:.2f}) "
                f"in job {job.id}."
            ),
            dedupe_key=f"rule:{rule.id}:item:{item.id}:confirmed",
            link_path=f"/history/{job.id}",
            field_id=job.field_id,
            mission_id=job.mission_id,
            detection_job_id=job.id,
            metadata_json={"label": item.label, "confidence": round(item.confidence, 4)},
        )
        if alert:
            created.append(alert)
    return created


def evaluate_mission_status_event(
    db: Session,
    settings: Settings,
    mission: Mission,
    previous_status: str,
    new_status: str,
) -> list[Alert]:
    """Evaluate mission_status_changed rules on mission state transition."""
    if mission.owner_id is None or previous_status == new_status:
        return []

    rules = list(
        db.scalars(
            select(AlertRule).where(
                AlertRule.owner_id == mission.owner_id,
                AlertRule.enabled.is_(True),
                AlertRule.trigger_type == "mission_status_changed",
            )
        ).all()
    )
    created: list[Alert] = []
    for rule in rules:
        if rule.field_id is not None and rule.field_id != mission.field_id:
            continue
        if rule.device_id is not None and rule.device_id != mission.device_id:
            continue
        if rule.target_mission_statuses and new_status not in rule.target_mission_statuses:
            continue
        alert = _create_alert_if_not_deduped(
            db,
            settings,
            rule=rule,
            owner_id=mission.owner_id,
            severity=rule.severity,
            category="mission_status_changed",
            title=f"Mission '{mission.title}' -> {new_status}",
            message=f"Mission {mission.id} transitioned from {previous_status} to {new_status}.",
            dedupe_key=f"rule:{rule.id}:mission:{mission.id}:status:{new_status}",
            link_path="/missions",
            field_id=mission.field_id,
            device_id=mission.device_id,
            mission_id=mission.id,
            metadata_json={"previous_status": previous_status, "new_status": new_status},
        )
        if alert:
            created.append(alert)
    return created


def record_gateway_connectivity_event(
    db: Session,
    gateway: EdgeGateway,
    *,
    event_type: str,
    detail: str | None = None,
) -> GatewayConnectivityEvent:
    """Persist a real gateway connectivity event."""
    ev = GatewayConnectivityEvent(
        gateway_id=gateway.id,
        device_id=gateway.device_id,
        owner_id=gateway.owner_id,
        event_type=event_type,
        camera_reachable=gateway.camera_reachable,
        internet_reachable=gateway.internet_reachable,
        camera_fps=gateway.camera_fps,
        dropped_frames=gateway.dropped_frames,
        detail=detail,
    )
    db.add(ev)
    return ev


def evaluate_gateway_offline_ttl(
    db: Session,
    settings: Settings,
    *,
    owner_id: uuid.UUID | None = None,
) -> tuple[int, int, int]:
    """Check active gateways against heartbeat TTL; record offline events & trigger rules."""
    now = datetime.now(UTC)
    ttl = timedelta(seconds=settings.gateway_heartbeat_ttl_seconds)

    gw_stmt = select(EdgeGateway).where(
        EdgeGateway.status == "active",
        EdgeGateway.last_heartbeat_at.is_not(None),
    )
    if owner_id is not None:
        gw_stmt = gw_stmt.where(EdgeGateway.owner_id == owner_id)
    gateways = list(db.scalars(gw_stmt).all())

    offline_detected = 0
    alerts_created = 0

    for gw in gateways:
        last_hb = _as_utc(gw.last_heartbeat_at)
        if last_hb is None or (now - last_hb) <= ttl:
            continue

        offline_detected += 1
        # Record connectivity event once per offline episode (since last heartbeat)
        already_logged = db.scalar(
            select(GatewayConnectivityEvent).where(
                GatewayConnectivityEvent.gateway_id == gw.id,
                GatewayConnectivityEvent.event_type == "offline_ttl_exceeded",
                GatewayConnectivityEvent.created_at >= last_hb,
            )
        )
        if already_logged is None:
            record_gateway_connectivity_event(
                db,
                gw,
                event_type="offline_ttl_exceeded",
                detail=f"Heartbeat missed beyond {settings.gateway_heartbeat_ttl_seconds}s TTL.",
            )

        if gw.owner_id is None:
            continue

        rules = list(
            db.scalars(
                select(AlertRule).where(
                    AlertRule.owner_id == gw.owner_id,
                    AlertRule.enabled.is_(True),
                    AlertRule.trigger_type == "gateway_offline_ttl",
                )
            ).all()
        )
        for rule in rules:
            if rule.device_id is not None and rule.device_id != gw.device_id:
                continue
            alert = _create_alert_if_not_deduped(
                db,
                settings,
                rule=rule,
                owner_id=gw.owner_id,
                severity=rule.severity,
                category="gateway_offline_ttl",
                title=f"Gateway offline: {gw.name}",
                message=(
                    f"Edge gateway '{gw.name}' ({gw.gateway_identifier}) exceeded the "
                    f"{settings.gateway_heartbeat_ttl_seconds}s heartbeat TTL."
                ),
                dedupe_key=f"rule:{rule.id}:gateway:{gw.id}:offline",
                link_path="/monitoring",
                device_id=gw.device_id,
                gateway_id=gw.id,
                metadata_json={
                    "gateway_identifier": gw.gateway_identifier,
                    "last_heartbeat_at": last_hb.isoformat(),
                    "ttl_seconds": settings.gateway_heartbeat_ttl_seconds,
                },
            )
            if alert is not None:
                alerts_created += 1

    db.flush()
    return len(gateways), offline_detected, alerts_created
