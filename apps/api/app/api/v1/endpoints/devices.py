"""Device Management CRUD endpoints honoring isolated ESP32-CAM AP boundaries."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentUserDep,
    DBSessionDep,
    OperatorWriterDep,
    enforce_owner_or_admin,
)
from app.core.audit import record_audit_event
from app.core.exceptions import ConflictError, NotFoundError
from app.models.device import Device
from app.models.field import Field
from app.schemas.common import PaginatedResponse
from app.schemas.domain import DeviceCreate, DeviceRead, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


def _validate_assigned_field(
    db: DBSessionDep,
    field_id: uuid.UUID | None,
    current_user: CurrentUserDep,
) -> None:
    if field_id is None:
        return
    field = db.get(Field, field_id)
    if field is None:
        raise NotFoundError("Assigned field", str(field_id))
    enforce_owner_or_admin(field.owner_id, current_user)


@router.get("", response_model=PaginatedResponse[DeviceRead], summary="List registered devices")
def list_devices(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None = Query(default=None, max_length=120),
    device_type: str | None = Query(default=None, max_length=48),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    field_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[DeviceRead]:
    stmt = select(Device)
    count_stmt = select(func.count()).select_from(Device)

    if current_user.role != "admin":
        stmt = stmt.where(Device.owner_id == current_user.id)
        count_stmt = count_stmt.where(Device.owner_id == current_user.id)

    if q:
        pattern = f"%{q.strip()}%"
        cond = or_(
            Device.name.ilike(pattern),
            Device.device_identifier.ilike(pattern),
            Device.hardware_model.ilike(pattern),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
        count_stmt = count_stmt.where(Device.device_type == device_type)

    if status_filter:
        stmt = stmt.where(Device.status == status_filter)
        count_stmt = count_stmt.where(Device.status == status_filter)

    if field_id is not None:
        stmt = stmt.where(Device.assigned_field_id == field_id)
        count_stmt = count_stmt.where(Device.assigned_field_id == field_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Device.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[DeviceRead](
        items=[DeviceRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a physical hardware device (never probed directly over RFC-1918)",
)
def create_device(
    payload: DeviceCreate,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> DeviceRead:
    _validate_assigned_field(db, payload.assigned_field_id, current_user)

    conn_cfg = dict(payload.connection_config)
    if payload.local_ssid and "local_ssid" not in conn_cfg:
        conn_cfg["local_ssid"] = payload.local_ssid
    if payload.local_endpoint_url and "local_dashboard_url" not in conn_cfg:
        conn_cfg["local_dashboard_url"] = payload.local_endpoint_url

    # Devices are NEVER marked "online" simply because they are created in the DB.
    device = Device(
        owner_id=current_user.id,
        assigned_field_id=payload.assigned_field_id,
        name=payload.name.strip(),
        device_type=payload.device_type,
        device_identifier=payload.device_identifier.strip(),
        hardware_model=payload.hardware_model.strip(),
        connectivity_mode=payload.connectivity_mode,
        status=payload.status,
        local_ssid=payload.local_ssid,
        local_endpoint_url=payload.local_endpoint_url,
        connection_config=conn_cfg,
        capabilities=dict(payload.capabilities),
        notes=payload.notes,
        last_authenticated_contact_at=None,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A device with identifier '{payload.device_identifier}' already exists."
        ) from exc

    record_audit_event(
        db,
        action="device.create",
        resource_type="device",
        resource_id=device.id,
        actor=current_user,
        request=request,
        metadata={
            "device_identifier": device.device_identifier,
            "connectivity_mode": device.connectivity_mode,
            "status": device.status,
        },
    )
    db.commit()
    db.refresh(device)
    return DeviceRead.model_validate(device)


@router.get("/{device_id}", response_model=DeviceRead, summary="Retrieve a device by ID")
def get_device(
    device_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> DeviceRead:
    device = db.get(Device, device_id)
    if device is None:
        raise NotFoundError("Device", str(device_id))
    enforce_owner_or_admin(device.owner_id, current_user)
    return DeviceRead.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceRead, summary="Update device record")
def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> DeviceRead:
    device = db.get(Device, device_id)
    if device is None:
        raise NotFoundError("Device", str(device_id))
    enforce_owner_or_admin(device.owner_id, current_user)

    if payload.unassign_field:
        device.assigned_field_id = None
    elif payload.assigned_field_id is not None:
        _validate_assigned_field(db, payload.assigned_field_id, current_user)
        device.assigned_field_id = payload.assigned_field_id

    if payload.name is not None:
        device.name = payload.name.strip()
    if payload.device_type is not None:
        device.device_type = payload.device_type
    if payload.device_identifier is not None:
        device.device_identifier = payload.device_identifier.strip()
    if payload.hardware_model is not None:
        device.hardware_model = payload.hardware_model.strip()
    if payload.connectivity_mode is not None:
        device.connectivity_mode = payload.connectivity_mode
    if payload.status is not None:
        device.status = payload.status
    if payload.local_ssid is not None:
        device.local_ssid = payload.local_ssid
    if payload.local_endpoint_url is not None:
        device.local_endpoint_url = payload.local_endpoint_url
    if payload.connection_config is not None:
        device.connection_config = dict(payload.connection_config)
    if payload.capabilities is not None:
        device.capabilities = dict(payload.capabilities)
    if payload.notes is not None:
        device.notes = payload.notes

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A device with identifier '{device.device_identifier}' already exists."
        ) from exc

    record_audit_event(
        db,
        action="device.update",
        resource_type="device",
        resource_id=device.id,
        actor=current_user,
        request=request,
        metadata={"status": device.status},
    )
    db.commit()
    db.refresh(device)
    return DeviceRead.model_validate(device)


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a registered device",
)
def delete_device(
    device_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> Response:
    device = db.get(Device, device_id)
    if device is None:
        raise NotFoundError("Device", str(device_id))
    enforce_owner_or_admin(device.owner_id, current_user)

    identifier = device.device_identifier
    db.delete(device)
    record_audit_event(
        db,
        action="device.delete",
        resource_type="device",
        resource_id=device_id,
        actor=current_user,
        request=request,
        metadata={"device_identifier": identifier},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
