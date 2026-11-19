"""Phase 5 Alert Rules, Operational Alerts, and Notification Center endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DBSessionDep, SettingsDep, require_roles
from app.core.audit import record_audit_event
from app.models import Alert, AlertRule, Notification
from app.schemas.alerts import (
    AlertPhase5Read,
    AlertResolveRequest,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
    GatewayEvaluationResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    UnreadCountResponse,
)
from app.schemas.common import PaginatedResponse
from app.services.alerts import (
    evaluate_gateway_offline_ttl,
    get_or_create_notification_preferences,
    validate_rule_configuration,
)

router = APIRouter(tags=["alerts"])

RuleWriteRole = Depends(require_roles("admin", "agronomist", "operator"))


def _ensure_alert_access(user: CurrentUserDep, alert: Alert) -> None:
    if user.role != "admin" and alert.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Alert access denied.")


def _ensure_rule_access(user: CurrentUserDep, rule: AlertRule) -> None:
    if user.role != "admin" and rule.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Alert rule access denied."
        )


@router.get(
    "/alerts",
    response_model=PaginatedResponse[AlertPhase5Read],
    summary="List operational alerts scoped to the user",
)
def list_alerts(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AlertPhase5Read]:
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)
    if current_user.role != "admin":
        stmt = stmt.where(Alert.owner_id == current_user.id)
        count_stmt = count_stmt.where(Alert.owner_id == current_user.id)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
        count_stmt = count_stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
        count_stmt = count_stmt.where(Alert.severity == severity)
    if category:
        stmt = stmt.where(Alert.category == category)
        count_stmt = count_stmt.where(Alert.category == category)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Alert.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[AlertPhase5Read](
        items=[AlertPhase5Read.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/alerts/evaluate-gateways",
    response_model=GatewayEvaluationResponse,
    summary="Evaluate gateway heartbeat TTLs and trigger offline alerts",
)
def evaluate_gateways(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayEvaluationResponse:
    owner_scope = None if current_user.role == "admin" else current_user.id
    checked, offline_count, created = evaluate_gateway_offline_ttl(
        db, settings, owner_id=owner_scope
    )
    db.commit()
    return GatewayEvaluationResponse(
        checked_gateways=checked,
        offline_detected=offline_count,
        alerts_created=created,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertPhase5Read,
    summary="Acknowledge an operational alert",
    dependencies=[RuleWriteRole],
)
def acknowledge_alert(
    alert_id: uuid.UUID,
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> AlertPhase5Read:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    _ensure_alert_access(current_user, alert)
    if alert.status == "open":
        alert.status = "acknowledged"
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = datetime.now(UTC)
        record_audit_event(
            db,
            action="alert.acknowledge",
            resource_type="alert",
            resource_id=alert.id,
            actor=current_user,
            request=request,
        )
        db.commit()
        db.refresh(alert)
    return AlertPhase5Read.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertPhase5Read,
    summary="Resolve an operational alert",
    dependencies=[RuleWriteRole],
)
def resolve_alert(
    alert_id: uuid.UUID,
    payload: AlertResolveRequest,
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> AlertPhase5Read:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    _ensure_alert_access(current_user, alert)
    alert.status = "resolved"
    alert.resolved_by = current_user.id
    alert.resolved_at = datetime.now(UTC)
    if payload.resolution_notes is not None:
        alert.resolution_notes = payload.resolution_notes
    if alert.acknowledged_at is None:
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = alert.resolved_at
    record_audit_event(
        db,
        action="alert.resolve",
        resource_type="alert",
        resource_id=alert.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(alert)
    return AlertPhase5Read.model_validate(alert)


@router.get(
    "/alert-rules",
    response_model=PaginatedResponse[AlertRuleRead],
    summary="List configurable alert rules",
)
def list_alert_rules(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AlertRuleRead]:
    stmt = select(AlertRule)
    count_stmt = select(func.count()).select_from(AlertRule)
    if current_user.role != "admin":
        stmt = stmt.where(AlertRule.owner_id == current_user.id)
        count_stmt = count_stmt.where(AlertRule.owner_id == current_user.id)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(AlertRule.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[AlertRuleRead](
        items=[AlertRuleRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/alert-rules",
    response_model=AlertRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a configurable alert rule",
    dependencies=[RuleWriteRole],
)
def create_alert_rule(
    payload: AlertRuleCreate,
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> AlertRuleRead:
    validate_rule_configuration(
        payload.trigger_type, payload.target_classes, payload.min_confidence
    )
    rule = AlertRule(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        severity=payload.severity,
        trigger_type=payload.trigger_type,
        target_classes=payload.target_classes,
        min_confidence=payload.min_confidence,
        target_mission_statuses=payload.target_mission_statuses,
        field_id=payload.field_id,
        device_id=payload.device_id,
        cooldown_minutes=payload.cooldown_minutes,
    )
    db.add(rule)
    db.flush()
    record_audit_event(
        db,
        action="alert_rule.create",
        resource_type="alert_rule",
        resource_id=rule.id,
        actor=current_user,
        request=request,
        metadata={"trigger_type": rule.trigger_type, "severity": rule.severity},
    )
    db.commit()
    db.refresh(rule)
    return AlertRuleRead.model_validate(rule)


@router.patch(
    "/alert-rules/{rule_id}",
    response_model=AlertRuleRead,
    summary="Update or toggle an alert rule",
    dependencies=[RuleWriteRole],
)
def update_alert_rule(
    rule_id: uuid.UUID,
    payload: AlertRuleUpdate,
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> AlertRuleRead:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found.")
    _ensure_rule_access(current_user, rule)

    updates = payload.model_dump(exclude_unset=True)
    new_classes = updates.get("target_classes", rule.target_classes)
    new_min_conf = updates.get("min_confidence", rule.min_confidence)
    validate_rule_configuration(rule.trigger_type, new_classes, new_min_conf)

    for key, val in updates.items():
        setattr(rule, key, val)

    record_audit_event(
        db,
        action="alert_rule.update",
        resource_type="alert_rule",
        resource_id=rule.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(rule)
    return AlertRuleRead.model_validate(rule)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert rule",
    dependencies=[RuleWriteRole],
)
def delete_alert_rule(
    rule_id: uuid.UUID,
    request: Request,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> None:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found.")
    _ensure_rule_access(current_user, rule)
    record_audit_event(
        db,
        action="alert_rule.delete",
        resource_type="alert_rule",
        resource_id=rule.id,
        actor=current_user,
        request=request,
    )
    db.delete(rule)
    db.commit()


@router.get(
    "/notifications",
    response_model=PaginatedResponse[NotificationRead],
    summary="List in-app notifications for the current user",
)
def list_notifications(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    unread_only: bool = Query(default=False),
    severity: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[NotificationRead]:
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    count_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
        count_stmt = count_stmt.where(Notification.is_read.is_(False))
    if severity:
        stmt = stmt.where(Notification.severity == severity)
        count_stmt = count_stmt.where(Notification.severity == severity)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[NotificationRead](
        items=[NotificationRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread notification count for the current user",
)
def get_unread_count(
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> UnreadCountResponse:
    count = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        )
        or 0
    )
    return UnreadCountResponse(unread_count=count)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> NotificationRead:
    notif = db.get(Notification, notification_id)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
    if notif.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Notification access denied."
        )
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(notif)
    return NotificationRead.model_validate(notif)


@router.post(
    "/notifications/read-all",
    response_model=UnreadCountResponse,
    summary="Mark all notifications as read for the current user",
)
def mark_all_notifications_read(
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> UnreadCountResponse:
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == current_user.id, Notification.is_read.is_(False)
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return UnreadCountResponse(unread_count=0)


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferenceRead,
    summary="Get notification preferences and honest SMTP availability",
)
def get_notification_preferences(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> NotificationPreferenceRead:
    pref = get_or_create_notification_preferences(db, current_user.id)
    db.commit()
    return NotificationPreferenceRead(
        in_app_enabled=pref.in_app_enabled,
        email_enabled=pref.email_enabled if settings.smtp_configured else False,
        email_address=pref.email_address,
        min_severity=pref.min_severity,
        muted_trigger_types=pref.muted_trigger_types or [],
        email_available=settings.smtp_configured,
        email_status_reason=(
            "SMTP provider configured."
            if settings.smtp_configured
            else "SMTP email delivery is unavailable because SMTP_HOST and SMTP_FROM_EMAIL are not configured."
        ),
    )


@router.patch(
    "/notifications/preferences",
    response_model=NotificationPreferenceRead,
    summary="Update notification preferences",
)
def update_notification_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> NotificationPreferenceRead:
    pref = get_or_create_notification_preferences(db, current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("email_enabled") is True and not settings.smtp_configured:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot enable email notifications: SMTP_HOST and SMTP_FROM_EMAIL are not configured.",
        )
    for key, val in updates.items():
        setattr(pref, key, val)
    db.commit()
    db.refresh(pref)
    return NotificationPreferenceRead(
        in_app_enabled=pref.in_app_enabled,
        email_enabled=pref.email_enabled if settings.smtp_configured else False,
        email_address=pref.email_address,
        min_severity=pref.min_severity,
        muted_trigger_types=pref.muted_trigger_types or [],
        email_available=settings.smtp_configured,
        email_status_reason=(
            "SMTP provider configured."
            if settings.smtp_configured
            else "SMTP email delivery is unavailable because SMTP_HOST and SMTP_FROM_EMAIL are not configured."
        ),
    )
