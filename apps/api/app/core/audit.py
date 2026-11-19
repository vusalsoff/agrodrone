"""Audit logging utility for sensitive security and domain mutations."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.rate_limit import extract_client_ip
from app.models.audit_log import AuditLog
from app.models.user import User

logger = get_logger(__name__)

_REDACTED_KEYS = frozenset({"password", "password_hash", "token", "refresh_token", "secret", "csrf_token"})


def _sanitize_metadata(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _REDACTED_KEYS:
            clean[key] = "[REDACTED]"
        else:
            clean[key] = value
    return clean


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    actor: User | None = None,
    actor_email: str | None = None,
    request: Request | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist a structured audit log entry without exposing credentials or tokens."""
    safe_meta = _sanitize_metadata(metadata)
    ip_address = extract_client_ip(request) if request is not None else None
    request_id = getattr(request.state, "request_id", None) if request is not None else None

    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        ip_address=ip_address,
        request_id=request_id,
        metadata_json=safe_meta,
    )
    db.add(entry)
    logger.info(
        "audit_event",
        action=action,
        resource_type=resource_type,
        resource_id=entry.resource_id,
        actor_id=str(actor.id) if actor else None,
        ip_address=ip_address,
    )
    return entry
