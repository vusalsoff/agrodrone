"""Phase 4 Field Edge Gateway endpoints: enrollment, credentials, heartbeat, stream relay & snapshots."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentUserDep,
    DBSessionDep,
    OperatorWriterDep,
    SettingsDep,
    enforce_owner_or_admin,
)
from app.core.audit import record_audit_event
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    FeatureNotEnabledError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationAppError,
)
from app.core.security import constant_time_equals, hash_opaque_token
from app.models.detection import DetectionItem, DetectionJob
from app.models.device import Device
from app.models.edge_gateway import EdgeGateway, StreamSession
from app.models.media import MediaAsset
from app.schemas.common import PaginatedResponse
from app.schemas.detection import DetectionJobDetailRead, DetectionJobRead
from app.schemas.domain import MediaAssetRead
from app.schemas.gateway import (
    GatewayDiagnosticsResponse,
    GatewayEnrollRequest,
    GatewayEnrollResponse,
    GatewayHeartbeatRequest,
    GatewayHeartbeatResponse,
    GatewayRead,
    LatestGatewayDetectionItem,
    LatestGatewayDetectionResponse,
    LocalCaptureAnalyzeRequest,
    SnapshotAnalyzeRequest,
    StreamSessionRead,
    StreamStartRequest,
)
from app.services.gateway_relay import (
    frame_relay_store,
    gateway_replay_guard,
    generate_gateway_credential,
    is_stream_session_active,
    to_gateway_read,
)
from app.services.media_security import detect_mime_from_magic_bytes, validate_uploaded_bytes
from app.services.storage import StorageAdapter
from app.services.vision import dispatch_detection_job, resolve_available_model

router = APIRouter(prefix="/gateway", tags=["gateway"])


def _authenticate_gateway(
    request: Request,
    db: DBSessionDep,
    x_gateway_token: Annotated[str | None, Header(alias="X-Gateway-Token")] = None,
    x_gateway_timestamp: Annotated[str | None, Header(alias="X-Gateway-Timestamp")] = None,
    x_gateway_nonce: Annotated[str | None, Header(alias="X-Gateway-Nonce")] = None,
) -> EdgeGateway:
    """Authenticate an outbound Edge Gateway daemon request using its SHA-256 hashed secret."""
    if not x_gateway_token or not x_gateway_token.startswith("agw_"):
        raise AuthenticationError("Valid X-Gateway-Token header is required.")

    token_hash = hash_opaque_token(x_gateway_token.strip())
    gateway = db.scalar(select(EdgeGateway).where(EdgeGateway.credential_hash == token_hash))
    if gateway is None or not constant_time_equals(gateway.credential_hash, token_hash):
        raise AuthenticationError("Gateway credential is invalid.")

    if gateway.status == "revoked":
        raise AuthenticationError("Gateway credential has been revoked.")

    gateway_replay_guard.verify_and_record(
        str(gateway.id),
        timestamp_header=x_gateway_timestamp,
        nonce_header=x_gateway_nonce,
    )
    return gateway


GatewayAuthDep = Annotated[EdgeGateway, Depends(_authenticate_gateway)]


def _get_latest_active_session(
    db: DBSessionDep, gateway_id: uuid.UUID
) -> StreamSession | None:
    session = db.scalar(
        select(StreamSession)
        .where(StreamSession.gateway_id == gateway_id, StreamSession.status == "active")
        .order_by(StreamSession.created_at.desc())
    )
    if session is None:
        return None
    if not is_stream_session_active(session):
        session.status = "expired"
        db.commit()
        return None
    return session


# ---------------------------------------------------------------------------
# User / Operator Gateway Management Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[GatewayRead], summary="List enrolled Edge Gateways")
def list_gateways(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[GatewayRead]:
    stmt = select(EdgeGateway)
    count_stmt = select(func.count()).select_from(EdgeGateway)
    if current_user.role != "admin":
        stmt = stmt.where(EdgeGateway.owner_id == current_user.id)
        count_stmt = count_stmt.where(EdgeGateway.owner_id == current_user.id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(EdgeGateway.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[GatewayRead](
        items=[to_gateway_read(row, settings) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/enroll",
    response_model=GatewayEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a Field Edge Gateway and issue a one-time scoped credential",
)
def enroll_gateway(
    payload: GatewayEnrollRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayEnrollResponse:
    if payload.device_id is not None:
        device = db.get(Device, payload.device_id)
        if device is None:
            raise NotFoundError("Device", str(payload.device_id))
        enforce_owner_or_admin(device.owner_id, current_user)

    raw_token, prefix, token_hash = generate_gateway_credential()
    gateway = EdgeGateway(
        owner_id=current_user.id,
        device_id=payload.device_id,
        name=payload.name.strip(),
        gateway_identifier=payload.gateway_identifier.strip(),
        deployment_mode=payload.deployment_mode,
        credential_prefix=prefix,
        credential_hash=token_hash,
        credential_version=1,
        status="enrolled",
        camera_reachable=False,
    )
    db.add(gateway)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A gateway with identifier '{payload.gateway_identifier}' already exists."
        ) from exc

    record_audit_event(
        db,
        action="gateway.enroll",
        resource_type="edge_gateway",
        resource_id=gateway.id,
        actor=current_user,
        request=request,
        metadata={
            "gateway_identifier": gateway.gateway_identifier,
            "deployment_mode": gateway.deployment_mode,
            "credential_prefix": prefix,
        },
    )
    from app.services.alerts import record_gateway_connectivity_event

    record_gateway_connectivity_event(
        db,
        gateway,
        event_type="enrolled",
        detail=f"Enrolled in {gateway.deployment_mode} mode.",
    )
    db.commit()
    db.refresh(gateway)
    return GatewayEnrollResponse(
        gateway=to_gateway_read(gateway, settings),
        gateway_token=raw_token,
    )


@router.post(
    "/{gateway_id}/rotate",
    response_model=GatewayEnrollResponse,
    summary="Rotate a gateway's credential and invalidate the previous token",
)
def rotate_gateway_credential(
    gateway_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayEnrollResponse:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)
    if gateway.status == "revoked":
        raise ConflictError("Cannot rotate credentials for a revoked gateway.")

    raw_token, prefix, token_hash = generate_gateway_credential()
    gateway.credential_prefix = prefix
    gateway.credential_hash = token_hash
    gateway.credential_version += 1

    record_audit_event(
        db,
        action="gateway.credential_rotate",
        resource_type="edge_gateway",
        resource_id=gateway.id,
        actor=current_user,
        request=request,
        metadata={"credential_version": gateway.credential_version, "credential_prefix": prefix},
    )
    db.commit()
    db.refresh(gateway)
    return GatewayEnrollResponse(
        gateway=to_gateway_read(gateway, settings),
        gateway_token=raw_token,
    )


@router.post(
    "/{gateway_id}/revoke",
    response_model=GatewayRead,
    summary="Revoke a gateway credential and close active stream sessions",
)
def revoke_gateway(
    gateway_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayRead:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    now = datetime.now(UTC)
    gateway.status = "revoked"
    gateway.revoked_at = now
    gateway.camera_reachable = False

    active_sessions = db.scalars(
        select(StreamSession).where(
            StreamSession.gateway_id == gateway.id, StreamSession.status == "active"
        )
    ).all()
    for sess in active_sessions:
        sess.status = "stopped"
        sess.stopped_at = now

    frame_relay_store.clear(gateway.id)
    from app.services.alerts import record_gateway_connectivity_event

    record_gateway_connectivity_event(
        db,
        gateway,
        event_type="revoked",
        detail="Gateway credential revoked by operator.",
    )
    record_audit_event(
        db,
        action="gateway.revoke",
        resource_type="edge_gateway",
        resource_id=gateway.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(gateway)
    return to_gateway_read(gateway, settings)


@router.get(
    "/{gateway_id}/diagnostics",
    response_model=GatewayDiagnosticsResponse,
    summary="Inspect gateway link diagnostics, heartbeat freshness, and network guidance",
)
def get_gateway_diagnostics(
    gateway_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayDiagnosticsResponse:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    session = _get_latest_active_session(db, gateway.id)
    gw_read = to_gateway_read(gateway, settings)

    if gateway.deployment_mode == "local_dev":
        guidance = (
            "Mode A (Local Dev): Connect this Windows machine to Wi-Fi SSID 'agroDrone' and run "
            "the gateway against http://127.0.0.1:8000. No internet connection is required."
        )
    else:
        guidance = (
            "Mode B (Remote Cloud): Gateway requires two interfaces (e.g., Wi-Fi on 'agroDrone' "
            "192.168.4.x + USB LTE/Ethernet uplink) to relay frames over outbound HTTPS."
        )

    return GatewayDiagnosticsResponse(
        gateway=gw_read,
        active_session=StreamSessionRead.model_validate(session) if session else None,
        heartbeat_ttl_seconds=settings.gateway_heartbeat_ttl_seconds,
        network_guidance=guidance,
        esp32_ap_ssid=settings.esp32_default_ap_ssid,
        esp32_local_url=settings.esp32_default_base_url,
        esp32_stream_url=settings.esp32_default_stream_url,
        direct_cloud_probe_allowed=settings.allow_direct_local_camera_probe,
    )


@router.post(
    "/{gateway_id}/stream/start",
    response_model=StreamSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Authorize a bounded live MJPEG frame relay session",
)
def start_stream_session(
    gateway_id: uuid.UUID,
    payload: StreamStartRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> StreamSessionRead:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    if gateway.status == "revoked":
        raise ConflictError("Cannot start stream for a revoked gateway.")

    now = datetime.now(UTC)
    existing = _get_latest_active_session(db, gateway.id)
    if existing is not None:
        return StreamSessionRead.model_validate(existing)

    active_count = (
        db.scalar(
            select(func.count())
            .select_from(StreamSession)
            .where(StreamSession.status == "active", StreamSession.expires_at > now)
        )
        or 0
    )
    if active_count >= settings.gateway_max_stream_subscribers:
        raise ConflictError(
            f"Maximum concurrent stream sessions ({settings.gateway_max_stream_subscribers}) reached."
        )

    ttl = min(payload.duration_seconds, settings.gateway_stream_session_ttl_seconds)
    session = StreamSession(
        gateway_id=gateway.id,
        device_id=gateway.device_id,
        owner_id=current_user.id,
        status="active",
        target_fps=payload.target_fps,
        max_frame_bytes=min(payload.max_frame_bytes, settings.gateway_max_frame_bytes),
        expires_at=now + timedelta(seconds=ttl),
    )
    db.add(session)
    db.flush()

    record_audit_event(
        db,
        action="gateway.stream_start",
        resource_type="stream_session",
        resource_id=session.id,
        actor=current_user,
        request=request,
        metadata={"gateway_id": str(gateway.id), "target_fps": payload.target_fps},
    )
    db.commit()
    db.refresh(session)
    return StreamSessionRead.model_validate(session)


@router.post(
    "/{gateway_id}/stream/stop",
    response_model=StreamSessionRead | None,
    summary="Stop an active stream relay session",
)
def stop_stream_session(
    gateway_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> StreamSessionRead | None:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    now = datetime.now(UTC)
    sessions = db.scalars(
        select(StreamSession).where(
            StreamSession.gateway_id == gateway.id, StreamSession.status == "active"
        )
    ).all()
    last_stopped: StreamSession | None = None
    for sess in sessions:
        sess.status = "stopped"
        sess.stopped_at = now
        last_stopped = sess

    frame_relay_store.clear(gateway.id)
    from app.services.alerts import record_gateway_connectivity_event

    record_gateway_connectivity_event(
        db,
        gateway,
        event_type="revoked",
        detail="Gateway credential revoked by operator.",
    )
    record_audit_event(
        db,
        action="gateway.stream_stop",
        resource_type="edge_gateway",
        resource_id=gateway.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    return StreamSessionRead.model_validate(last_stopped) if last_stopped else None


@router.get(
    "/{gateway_id}/stream/latest",
    summary="Fetch the latest relayed JPEG frame for an authorized stream session",
)
def get_latest_relayed_frame(
    gateway_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> Response:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    session = _get_latest_active_session(db, gateway.id)
    if session is None:
        raise ConflictError("No active stream session for this gateway. Start a stream first.")

    buffered = frame_relay_store.get_latest(gateway.id)
    if buffered is None or buffered.session_id != session.id:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(
        content=buffered.jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Sequence": str(buffered.sequence),
            "X-Frame-Received-At": buffered.received_at.isoformat(),
        },
    )


@router.get(
    "/{gateway_id}/snapshots",
    response_model=PaginatedResponse[MediaAssetRead],
    summary="List captured ESP32-CAM snapshots associated with this gateway",
)
def list_gateway_snapshots(
    gateway_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MediaAssetRead]:
    gateway = db.get(EdgeGateway, gateway_id)
    if gateway is None:
        raise NotFoundError("Edge gateway", str(gateway_id))
    enforce_owner_or_admin(gateway.owner_id, current_user)

    marker = f"gateway:{gateway.id}"
    stmt = select(MediaAsset).where(MediaAsset.notes.ilike(f"%{marker}%"))
    count_stmt = select(func.count()).select_from(MediaAsset).where(
        MediaAsset.notes.ilike(f"%{marker}%")
    )
    if current_user.role != "admin":
        stmt = stmt.where(MediaAsset.uploaded_by == current_user.id)
        count_stmt = count_stmt.where(MediaAsset.uploaded_by == current_user.id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(MediaAsset.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[MediaAssetRead](
        items=[MediaAssetRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/snapshots/{media_id}/analyze",
    response_model=DetectionJobDetailRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run asynchronous YOLOv8n analysis on a captured ESP32-CAM snapshot",
)
def analyze_gateway_snapshot(
    media_id: uuid.UUID,
    payload: SnapshotAnalyzeRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> DetectionJobDetailRead:
    if not settings.ai_inference_enabled:
        raise FeatureNotEnabledError(
            feature="AgroVision AI inference",
            target_phase="Phase 3",
            reason="Set AI_INFERENCE_ENABLED=true to analyze snapshots.",
        )

    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)

    model_entry = resolve_available_model(payload.model_id)
    job = DetectionJob(
        owner_id=current_user.id,
        field_id=asset.field_id,
        mission_id=asset.mission_id,
        media_asset_id=asset.id,
        detection_mode=model_entry.detection_mode,
        model_id=model_entry.model_id,
        status="queued",
        progress_percent=0,
        media_type=asset.media_type,
        model_name=model_entry.name,
        model_version=model_entry.version,
        model_checksum=model_entry.actual_sha256,
        dataset_scope=model_entry.dataset_scope,
        device_used=settings.ai_device,
        confidence_threshold=payload.confidence_threshold,
        summary_json={"source": "esp32_edge_gateway_snapshot"},
    )
    db.add(job)
    db.flush()
    record_audit_event(
        db,
        action="gateway.snapshot_analyze",
        resource_type="detection_job",
        resource_id=job.id,
        actor=current_user,
        request=request,
        metadata={"media_asset_id": str(asset.id), "model_id": model_entry.model_id},
    )
    db.commit()

    dispatch_detection_job(job_id=job.id, db=db, settings=settings, run_async=True)
    db.refresh(job)
    return DetectionJobDetailRead(
        **DetectionJobRead.model_validate(job).model_dump(),
        items=[],
        media_asset=MediaAssetRead.model_validate(asset),
    )


# ---------------------------------------------------------------------------
# Outbound Gateway-Daemon Endpoints (Authenticated via X-Gateway-Token)
# ---------------------------------------------------------------------------


@router.post(
    "/heartbeat",
    response_model=GatewayHeartbeatResponse,
    summary="Receive authenticated gateway heartbeat and return active stream directive",
)
def gateway_heartbeat(
    payload: GatewayHeartbeatRequest,
    gateway: GatewayAuthDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> GatewayHeartbeatResponse:
    now = datetime.now(UTC)
    gateway.status = "active"
    gateway.camera_reachable = payload.camera_reachable
    gateway.camera_fps = payload.camera_fps
    gateway.dropped_frames = payload.dropped_frames
    gateway.queue_depth = payload.queue_depth
    gateway.queue_bytes = payload.queue_bytes
    if payload.internet_reachable is not None:
        gateway.internet_reachable = payload.internet_reachable
    if payload.deployment_mode is not None:
        gateway.deployment_mode = payload.deployment_mode
    if payload.local_interface is not None:
        gateway.local_interface = payload.local_interface
    if payload.uplink_interface is not None:
        gateway.uplink_interface = payload.uplink_interface
    gateway.diagnostics_json = dict(payload.diagnostics)
    gateway.last_heartbeat_at = now

    if gateway.device_id is not None:
        device = db.get(Device, gateway.device_id)
        if device is not None:
            device.last_authenticated_contact_at = now
            device.last_seen_at = now

    session = _get_latest_active_session(db, gateway.id)
    from app.services.alerts import record_gateway_connectivity_event

    record_gateway_connectivity_event(
        db,
        gateway,
        event_type="heartbeat_online",
        detail="Gateway heartbeat received.",
    )
    db.commit()

    return GatewayHeartbeatResponse(
        gateway_id=gateway.id,
        server_time=now,
        heartbeat_ttl_seconds=settings.gateway_heartbeat_ttl_seconds,
        stream_active=session is not None,
        active_session=StreamSessionRead.model_validate(session) if session else None,
    )


@router.post(
    "/stream/frame",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive one bounded live JPEG frame from an authenticated Edge Gateway",
)
async def ingest_stream_frame(
    gateway: GatewayAuthDep,
    db: DBSessionDep,
    file: UploadFile = File(...),
    sequence: int = Form(default=0),
) -> dict[str, object]:
    session = _get_latest_active_session(db, gateway.id)
    if session is None:
        raise ConflictError("No active stream session. Frame rejected.")

    raw = await file.read(session.max_frame_bytes + 1)
    if len(raw) == 0:
        raise ValidationAppError("Frame payload is empty.")
    if len(raw) > session.max_frame_bytes:
        raise PayloadTooLargeError(
            f"Frame exceeds session max_frame_bytes ({session.max_frame_bytes} bytes)."
        )

    detected = detect_mime_from_magic_bytes(raw[:32])
    if detected != "image/jpeg":
        raise ValidationAppError("Live relay frames must be valid JPEG binaries.")

    now = datetime.now(UTC)
    frame_relay_store.put_frame(
        gateway.id,
        session_id=session.id,
        jpeg_bytes=raw,
        sequence=sequence,
    )
    session.frames_relayed += 1
    session.last_frame_at = now
    gateway.last_heartbeat_at = now
    gateway.camera_reachable = True
    gateway.status = "active"
    db.commit()

    return {
        "accepted": True,
        "session_id": str(session.id),
        "frames_relayed": session.frames_relayed,
        "sequence": sequence,
    }


@router.post(
    "/snapshots",
    response_model=MediaAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a captured ESP32-CAM snapshot from an authenticated Edge Gateway",
)
async def ingest_gateway_snapshot(
    request: Request,
    gateway: GatewayAuthDep,
    db: DBSessionDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    notes: str | None = Form(default=None),
    analyze: bool = Form(default=False),
    model_id: str = Form(default="yolov8n-coco-general"),
    confidence_threshold: float = Form(default=0.35),
) -> MediaAssetRead:
    raw = await file.read(settings.max_image_upload_bytes + 1)
    if len(raw) > settings.max_image_upload_bytes:
        raise PayloadTooLargeError(
            f"Snapshot exceeds maximum allowed image size ({settings.max_image_upload_bytes} bytes)."
        )

    validated = validate_uploaded_bytes(
        filename=file.filename or "esp32_snapshot.jpg",
        declared_mime=file.content_type or "image/jpeg",
        content=raw,
        settings=settings,
    )
    if validated.media_type != "image":
        raise ValidationAppError("Gateway snapshot ingestion accepts image files only.")

    owner_id = gateway.owner_id
    field_id = None
    if gateway.device_id is not None:
        dev = db.get(Device, gateway.device_id)
        if dev is not None:
            field_id = dev.assigned_field_id

    storage = StorageAdapter(settings)
    storage_key = storage.build_storage_key(str(owner_id or "gateway"), validated.safe_filename)
    storage.put_bytes(storage_key, raw, validated.mime_type)

    marker = f"[gateway:{gateway.id}]"
    full_notes = f"{marker} {notes.strip()}".strip() if notes and notes.strip() else marker
    now = datetime.now(UTC)

    asset = MediaAsset(
        field_id=field_id,
        uploaded_by=owner_id,
        media_type="image",
        upload_status="uploaded",
        storage_backend=settings.storage_backend,
        storage_key=storage_key,
        safe_filename=validated.safe_filename,
        original_filename=validated.sanitized_original_name,
        mime_type=validated.mime_type,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        width_px=validated.width_px,
        height_px=validated.height_px,
        captured_at=now,
        geo_source="none",
        notes=full_notes[:2000],
    )
    db.add(asset)
    db.flush()

    gateway.last_heartbeat_at = now
    gateway.status = "active"
    record_audit_event(
        db,
        action="gateway.snapshot_ingest",
        resource_type="media_asset",
        resource_id=asset.id,
        request=request,
        metadata={"gateway_id": str(gateway.id), "byte_size": asset.byte_size},
    )

    created_job_id: uuid.UUID | None = None
    if analyze and settings.ai_inference_enabled:
        model_entry = resolve_available_model(model_id)
        job = DetectionJob(
            owner_id=owner_id,
            field_id=field_id,
            media_asset_id=asset.id,
            detection_mode=model_entry.detection_mode,
            model_id=model_entry.model_id,
            status="queued",
            progress_percent=0,
            media_type="image",
            model_name=model_entry.name,
            model_version=model_entry.version,
            model_checksum=model_entry.actual_sha256,
            dataset_scope=model_entry.dataset_scope,
            device_used=settings.ai_device,
            confidence_threshold=max(0.05, min(0.95, confidence_threshold)),
            summary_json={"source": "esp32_edge_gateway_snapshot"},
        )
        db.add(job)
        db.flush()
        created_job_id = job.id

    db.commit()
    if created_job_id is not None:
        dispatch_detection_job(job_id=created_job_id, db=db, settings=settings, run_async=True)

    db.refresh(asset)
    return MediaAssetRead.model_validate(asset)


@router.get(
    "/latest-detection",
    response_model=LatestGatewayDetectionResponse,
    summary="Return the latest YOLO detection job for authenticated Edge Gateway / Arduino consumers",
)
def get_latest_gateway_detection(
    gateway: GatewayAuthDep,
    db: DBSessionDep,
    settings: SettingsDep,
    model_id: str | None = Query(default=None),
) -> LatestGatewayDetectionResponse:
    """Expose fresh, non-fabricated detection state to authenticated hardware bridges."""
    now = datetime.now(UTC)
    stmt = select(DetectionJob)
    if gateway.owner_id is not None:
        stmt = stmt.where(DetectionJob.owner_id == gateway.owner_id)
    if model_id:
        stmt = stmt.where(DetectionJob.model_id == model_id)
    stmt = stmt.order_by(DetectionJob.created_at.desc()).limit(1)
    job = db.scalar(stmt)

    hb = gateway.last_heartbeat_at
    if hb is not None and hb.tzinfo is None:
        hb = hb.replace(tzinfo=UTC)
    hb_fresh = hb is not None and (now - hb).total_seconds() <= settings.gateway_heartbeat_ttl_seconds
    cam_ok = bool(gateway.camera_reachable and hb_fresh)

    if job is None:
        return LatestGatewayDetectionResponse(
            has_result=False,
            camera_reachable=cam_ok,
            ai_inference_enabled=settings.ai_inference_enabled,
        )

    completed_at = job.completed_at
    if completed_at is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    age_seconds = round(max(0.0, (now - completed_at).total_seconds()), 3) if completed_at else None

    items: list[LatestGatewayDetectionItem] = []
    if job.status == "completed":
        rows = db.scalars(select(DetectionItem).where(DetectionItem.job_id == job.id)).all()
        items = [LatestGatewayDetectionItem(label=row.label, confidence=row.confidence) for row in rows]

    return LatestGatewayDetectionResponse(
        has_result=True,
        job_id=job.id,
        status=job.status,
        model_id=job.model_id,
        created_at=job.created_at,
        completed_at=completed_at,
        age_seconds=age_seconds,
        camera_reachable=cam_ok,
        ai_inference_enabled=settings.ai_inference_enabled,
        detections=items,
    )


@router.post(
    "/local-capture-analyze",
    response_model=DetectionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def capture_local_esp32_and_analyze(
    payload: LocalCaptureAnalyzeRequest,
    request: Request,
    db: DBSessionDep,
    current_user: OperatorWriterDep,
    settings: SettingsDep,
) -> DetectionJobRead:
    """Capture a single frame from the local ESP32-CAM AP (192.168.4.1/capture) and run YOLO."""
    if not settings.ai_inference_enabled:
        raise FeatureNotEnabledError("AI inference is disabled by configuration.")

    model_entry = resolve_available_model(payload.model_id)
    capture_url = f"{settings.esp32_local_url.rstrip('/')}/capture"

    try:
        req = urllib.request.Request(capture_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read(settings.max_upload_bytes + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValidationAppError(
            f"Could not capture frame from ESP32-CAM ({capture_url}). "
            "Confirm Windows is connected to 'agroDrone' Wi-Fi.",
            details={"capture_url": capture_url, "error": str(exc)},
        ) from exc

    if len(raw) > settings.max_upload_bytes:
        raise PayloadTooLargeError("Captured frame exceeds maximum upload size.")

    validated = validate_uploaded_bytes(
        filename=f"esp32_local_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jpg",
        declared_mime="image/jpeg",
        content=raw,
        settings=settings,
    )
    if validated.media_type != "image":
        raise ValidationAppError("ESP32-CAM capture endpoint did not return a valid image.")

    storage = StorageAdapter(settings)
    storage_key = storage.build_storage_key(str(current_user.id), validated.safe_filename)
    storage.put_bytes(storage_key, raw, validated.mime_type)

    now = datetime.now(UTC)
    asset = MediaAsset(
        field_id=None,
        uploaded_by=current_user.id,
        media_type="image",
        upload_status="uploaded",
        storage_backend=settings.storage_backend,
        storage_key=storage_key,
        safe_filename=validated.safe_filename,
        original_filename=validated.sanitized_original_name,
        mime_type=validated.mime_type,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        width_px=validated.width_px,
        height_px=validated.height_px,
        captured_at=now,
        geo_source="none",
        notes="[local-esp32-capture] Captured directly from 192.168.4.1/capture",
    )
    db.add(asset)
    db.flush()

    job = DetectionJob(
        owner_id=current_user.id,
        field_id=None,
        media_asset_id=asset.id,
        detection_mode=model_entry.detection_mode,
        model_id=model_entry.model_id,
        status="queued",
        progress_percent=0,
        media_type="image",
        model_name=model_entry.name,
        model_version=model_entry.version,
        model_checksum=model_entry.actual_sha256,
        dataset_scope=model_entry.dataset_scope,
        device_used=settings.ai_device,
        confidence_threshold=payload.confidence_threshold,
        summary_json={"source": "esp32_local_capture"},
    )
    db.add(job)
    db.flush()

    record_audit_event(
        db,
        action="gateway.local_capture_analyze",
        resource_type="detection_job",
        resource_id=job.id,
        request=request,
        user=current_user,
        metadata={"model_id": model_entry.model_id, "asset_id": str(asset.id)},
    )
    db.commit()
    dispatch_detection_job(job_id=job.id, db=db, settings=settings, run_async=True)
    db.refresh(job)
    return DetectionJobRead.model_validate(job)
