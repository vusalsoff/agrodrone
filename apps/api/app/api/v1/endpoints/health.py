"""Liveness, readiness, and basic operational metrics endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select, text

from app.api.deps import DBSessionDep, SettingsDep
from app.core.logging import get_logger
from app.models import Alert, DetectionJob, EdgeGateway
from app.schemas.system import HealthResponse
from app.services.storage import StorageAdapter

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Service & database liveness check")
def health_check(db: DBSessionDep, settings: SettingsDep) -> HealthResponse:
    """Ping the database with SELECT 1 and return real latency and connection state."""
    start = perf_counter()
    db_connected = False
    latency_ms: float | None = None

    try:
        db.execute(text("SELECT 1"))
        db_connected = True
        latency_ms = round((perf_counter() - start) * 1000, 2)
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database_connected=db_connected,
        database_dialect=settings.database_dialect,
        database_latency_ms=latency_ms,
        timestamp=datetime.now(UTC),
    )


@router.get("/ready", summary="Production readiness probe (database + storage)")
def readiness_check(
    response: Response, db: DBSessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Return 200 when database and storage are ready; 503 when critical dependencies fail."""
    db_ready = False
    try:
        db.execute(text("SELECT 1"))
        db_ready = True
    except Exception as exc:
        logger.error("readiness_db_check_failed", error=str(exc))

    storage_health = StorageAdapter(settings).check_health()
    ready = db_ready and storage_health.ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": ready,
        "database_ready": db_ready,
        "storage_ready": storage_health.ready,
        "storage_backend": storage_health.backend,
        "ai_worker_mode": settings.ai_worker_mode,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/metrics", summary="Basic non-sensitive operational metrics")
def operational_metrics(db: DBSessionDep, settings: SettingsDep) -> dict[str, Any]:
    """Expose aggregate counts for monitoring without leaking PII, secrets, or media."""
    queued_jobs = (
        db.scalar(
            select(func.count())
            .select_from(DetectionJob)
            .where(DetectionJob.status == "queued")
        )
        or 0
    )
    processing_jobs = (
        db.scalar(
            select(func.count())
            .select_from(DetectionJob)
            .where(DetectionJob.status == "processing")
        )
        or 0
    )
    open_alerts = (
        db.scalar(
            select(func.count()).select_from(Alert).where(Alert.status == "open")
        )
        or 0
    )
    active_gateways = (
        db.scalar(
            select(func.count())
            .select_from(EdgeGateway)
            .where(EdgeGateway.status == "active")
        )
        or 0
    )
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "queued_detection_jobs": queued_jobs,
        "processing_detection_jobs": processing_jobs,
        "open_alerts": open_alerts,
        "active_edge_gateways": active_gateways,
        "timestamp": datetime.now(UTC).isoformat(),
    }
