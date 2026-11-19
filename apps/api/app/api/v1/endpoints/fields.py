"""Field Management CRUD endpoints with geodesic GeoJSON validation, ownership, and RBAC."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentUserDep,
    DBSessionDep,
    FieldWriterDep,
    enforce_owner_or_admin,
)
from app.core.audit import record_audit_event
from app.core.exceptions import ConflictError, NotFoundError
from app.models.field import Field
from app.schemas.common import PaginatedResponse
from app.schemas.domain import FieldCreate, FieldRead, FieldUpdate
from app.services.geo import validate_and_measure_polygon

router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("", response_model=PaginatedResponse[FieldRead], summary="List agricultural fields")
def list_fields(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None = Query(default=None, max_length=120),
    crop_type: str | None = Query(default=None, max_length=100),
    has_boundary: bool | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[FieldRead]:
    stmt = select(Field)
    count_stmt = select(func.count()).select_from(Field)

    if current_user.role != "admin":
        stmt = stmt.where(Field.owner_id == current_user.id)
        count_stmt = count_stmt.where(Field.owner_id == current_user.id)

    if q:
        pattern = f"%{q.strip()}%"
        search_cond = or_(
            Field.name.ilike(pattern),
            Field.code.ilike(pattern),
            Field.location.ilike(pattern),
            Field.crop_type.ilike(pattern),
        )
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    if crop_type:
        stmt = stmt.where(Field.crop_type.ilike(crop_type.strip()))
        count_stmt = count_stmt.where(Field.crop_type.ilike(crop_type.strip()))

    if has_boundary is True:
        stmt = stmt.where(Field.boundary_geojson.is_not(None))
        count_stmt = count_stmt.where(Field.boundary_geojson.is_not(None))
    elif has_boundary is False:
        stmt = stmt.where(Field.boundary_geojson.is_(None))
        count_stmt = count_stmt.where(Field.boundary_geojson.is_(None))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Field.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[FieldRead](
        items=[FieldRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=FieldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agricultural field parcel (Admin / Agronomist)",
)
def create_field(
    payload: FieldCreate,
    request: Request,
    current_user: FieldWriterDep,
    db: DBSessionDep,
) -> FieldRead:
    normalized_code = payload.code.upper()
    boundary_geojson = None
    area_hectares = payload.area_hectares
    centroid_lat = None
    centroid_lng = None

    if payload.boundary_geojson is not None:
        metrics = validate_and_measure_polygon(payload.boundary_geojson)
        boundary_geojson = metrics.normalized_geojson
        area_hectares = metrics.area_hectares
        centroid_lat = metrics.centroid_lat
        centroid_lng = metrics.centroid_lng

    field = Field(
        owner_id=current_user.id,
        name=payload.name,
        code=normalized_code,
        description=payload.description,
        location=payload.location,
        crop_type=payload.crop_type,
        area_hectares=area_hectares,
        boundary_geojson=boundary_geojson,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
        notes=payload.notes,
    )
    db.add(field)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"A field with code '{normalized_code}' already exists.") from exc

    record_audit_event(
        db,
        action="field.create",
        resource_type="field",
        resource_id=field.id,
        actor=current_user,
        request=request,
        metadata={"code": field.code, "has_boundary": boundary_geojson is not None},
    )
    db.commit()
    db.refresh(field)
    return FieldRead.model_validate(field)


@router.get("/{field_id}", response_model=FieldRead, summary="Retrieve a field by ID")
def get_field(
    field_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> FieldRead:
    field = db.get(Field, field_id)
    if field is None:
        raise NotFoundError("Field", str(field_id))
    enforce_owner_or_admin(field.owner_id, current_user)
    return FieldRead.model_validate(field)


@router.patch(
    "/{field_id}",
    response_model=FieldRead,
    summary="Update field details or geographic polygon boundary",
)
def update_field(
    field_id: uuid.UUID,
    payload: FieldUpdate,
    request: Request,
    current_user: FieldWriterDep,
    db: DBSessionDep,
) -> FieldRead:
    field = db.get(Field, field_id)
    if field is None:
        raise NotFoundError("Field", str(field_id))
    enforce_owner_or_admin(field.owner_id, current_user)

    if payload.name is not None:
        field.name = payload.name.strip()
    if payload.code is not None:
        field.code = payload.code.strip().upper()
    if payload.description is not None:
        field.description = payload.description
    if payload.location is not None:
        field.location = payload.location
    if payload.crop_type is not None:
        field.crop_type = payload.crop_type
    if payload.notes is not None:
        field.notes = payload.notes

    if payload.clear_boundary:
        field.boundary_geojson = None
        field.centroid_lat = None
        field.centroid_lng = None
        if payload.area_hectares is not None:
            field.area_hectares = payload.area_hectares
    elif payload.boundary_geojson is not None:
        metrics = validate_and_measure_polygon(payload.boundary_geojson)
        field.boundary_geojson = metrics.normalized_geojson
        field.area_hectares = metrics.area_hectares
        field.centroid_lat = metrics.centroid_lat
        field.centroid_lng = metrics.centroid_lng
    elif payload.area_hectares is not None:
        field.area_hectares = payload.area_hectares

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"A field with code '{field.code}' already exists.") from exc

    record_audit_event(
        db,
        action="field.update",
        resource_type="field",
        resource_id=field.id,
        actor=current_user,
        request=request,
        metadata={"code": field.code, "has_boundary": field.boundary_geojson is not None},
    )
    db.commit()
    db.refresh(field)
    return FieldRead.model_validate(field)


@router.delete(
    "/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a field parcel (Admin / Owner Agronomist)",
)
def delete_field(
    field_id: uuid.UUID,
    request: Request,
    current_user: FieldWriterDep,
    db: DBSessionDep,
) -> Response:
    field = db.get(Field, field_id)
    if field is None:
        raise NotFoundError("Field", str(field_id))
    enforce_owner_or_admin(field.owner_id, current_user)

    code = field.code
    db.delete(field)
    record_audit_event(
        db,
        action="field.delete",
        resource_type="field",
        resource_id=field_id,
        actor=current_user,
        request=request,
        metadata={"code": code},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
