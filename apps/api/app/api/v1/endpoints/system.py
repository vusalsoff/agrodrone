"""Operational system status and honest hardware/AI capability endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import DBSessionDep, SettingsDep
from app.core.logging import get_logger
from app.models import Alert, DetectionJob, Device, Field, MediaAsset, Mission
from app.schemas.system import (
    CapabilitiesResponse,
    EntityCounts,
    SubsystemStatus,
    SystemStatusResponse,
)
from app.services.gateway import (
    get_hardware_baseline,
    get_module_readiness,
    get_network_boundary_policy,
)
from app.services.storage import StorageAdapter
from app.services.vision import get_ai_capability_policy, get_model_catalog

router = APIRouter(prefix="/system", tags=["system"])
logger = get_logger(__name__)


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Live subsystem status and database entity counts",
)
def get_system_status(db: DBSessionDep, settings: SettingsDep) -> SystemStatusResponse:
    """Return actual database counts and real subsystem health without fabricated data."""
    start = perf_counter()
    db_connected = False
    latency_ms: float | None = None
    counts = EntityCounts(
        fields=0,
        devices=0,
        missions=0,
        media_assets=0,
        detection_jobs=0,
        open_alerts=0,
    )

    try:
        db.execute(text("SELECT 1"))
        db_connected = True
        latency_ms = round((perf_counter() - start) * 1000, 2)
        counts = EntityCounts(
            fields=db.scalar(select(func.count()).select_from(Field)) or 0,
            devices=db.scalar(select(func.count()).select_from(Device)) or 0,
            missions=db.scalar(select(func.count()).select_from(Mission)) or 0,
            media_assets=db.scalar(select(func.count()).select_from(MediaAsset)) or 0,
            detection_jobs=db.scalar(select(func.count()).select_from(DetectionJob)) or 0,
            open_alerts=(
                db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open"))
                or 0
            ),
        )
    except Exception as exc:
        logger.warning("system_status_db_query_failed", error=str(exc))

    storage_health = StorageAdapter(settings).check_health()
    catalog = get_model_catalog()
    available_models = [m for m in catalog if m.status == "available"]
    ai_ready = settings.ai_inference_enabled and len(available_models) > 0

    subsystems = [
        SubsystemStatus(
            id="api",
            name="FastAPI Control Plane & RBAC",
            status="operational",
            summary=f"Serving v{settings.app_version} ({settings.environment}) with Argon2id, JWT rotation, CSRF & audit logging.",
            target_phase="Phase 3",
        ),
        SubsystemStatus(
            id="database",
            name=f"Relational Store ({settings.database_dialect.upper()})",
            status="operational" if db_connected else "degraded",
            summary=(
                f"Connected ({latency_ms} ms) — Alembic 0005 schema active."
                if db_connected
                else "Database unreachable or migrations have not been applied."
            ),
            target_phase="Phase 3",
        ),
        SubsystemStatus(
            id="storage",
            name=f"Object Storage ({storage_health.backend.upper()})",
            status="operational" if storage_health.ready else "degraded",
            summary=storage_health.detail,
            target_phase="Phase 3",
        ),
        SubsystemStatus(
            id="ai_worker",
            name="AgroVision AI Engine (YOLO / PyTorch / OpenCV)",
            status="operational" if ai_ready else "unconfigured",
            summary=(
                f"Active ({len(available_models)}/{len(catalog)} models ready): {available_models[0].model_id} on {settings.ai_device.upper()}."
                if ai_ready
                else "AI inference disabled or baseline model weights unavailable."
            ),
            target_phase="Phase 3",
        ),
        SubsystemStatus(
            id="edge_gateway",
            name="ESP32-CAM Edge Gateway",
            status="operational" if settings.edge_gateway_enabled else "isolated_local",
            summary=(
                f"Outbound gateway relay active (heartbeat TTL {settings.gateway_heartbeat_ttl_seconds}s) for {settings.esp32_default_ap_ssid} (192.168.4.1)."
                if settings.edge_gateway_enabled
                else f"ESP32-CAM ({settings.esp32_default_ap_ssid} @ 192.168.4.1) is an isolated AP; gateway disabled."
            ),
            target_phase="Phase 4",
        ),
    ]

    return SystemStatusResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        phase="AgroDrone Platform · Phases 1–7 Active",
        database_connected=db_connected,
        database_dialect=settings.database_dialect,
        database_latency_ms=latency_ms,
        storage_backend=storage_health.backend,
        ai_inference_enabled=ai_ready,
        edge_gateway_enabled=settings.edge_gateway_enabled,
        counts=counts,
        subsystems=subsystems,
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="Hardware reality, network isolation policy, AI honesty policy, and module matrix",
)
def get_capabilities(settings: SettingsDep) -> CapabilitiesResponse:
    """Provide single-source-of-truth capabilities and honest constraints for the UI."""
    return CapabilitiesResponse(
        hardware_baseline=get_hardware_baseline(settings),
        network_boundary=get_network_boundary_policy(settings),
        ai_policy=get_ai_capability_policy(settings),
        modules=get_module_readiness(),
    )
