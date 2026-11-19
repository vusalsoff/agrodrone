"""Mission Management CRUD, strict state transitions, and manual operator observations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import func, or_, select

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
from app.models.mission import Mission
from app.schemas.common import PaginatedResponse
from app.schemas.domain import (
    MissionCreate,
    MissionObservationCreate,
    MissionRead,
    MissionTransitionRequest,
    MissionUpdate,
)

router = APIRouter(prefix="/missions", tags=["missions"])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planned", "in_progress", "cancelled"},
    "planned": {"draft", "in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": {"draft"},
}


def _validate_mission_references(
    db: DBSessionDep,
    *,
    field_id: uuid.UUID | None,
    device_id: uuid.UUID | None,
    current_user: CurrentUserDep,
) -> None:
    if field_id is not None:
        field = db.get(Field, field_id)
        if field is None:
            raise NotFoundError("Field", str(field_id))
        enforce_owner_or_admin(field.owner_id, current_user)

    if device_id is not None:
        device = db.get(Device, device_id)
        if device is None:
            raise NotFoundError("Device", str(device_id))
        enforce_owner_or_admin(device.owner_id, current_user)


@router.get("", response_model=PaginatedResponse[MissionRead], summary="List field missions")
def list_missions(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    field_id: uuid.UUID | None = Query(default=None),
    device_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MissionRead]:
    stmt = select(Mission)
    count_stmt = select(func.count()).select_from(Mission)

    if current_user.role != "admin":
        stmt = stmt.where(Mission.owner_id == current_user.id)
        count_stmt = count_stmt.where(Mission.owner_id == current_user.id)

    if q:
        pattern = f"%{q.strip()}%"
        cond = or_(
            Mission.title.ilike(pattern),
            Mission.description.ilike(pattern),
            Mission.operator_notes.ilike(pattern),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if status_filter:
        stmt = stmt.where(Mission.status == status_filter)
        count_stmt = count_stmt.where(Mission.status == status_filter)

    if field_id is not None:
        stmt = stmt.where(Mission.field_id == field_id)
        count_stmt = count_stmt.where(Mission.field_id == field_id)

    if device_id is not None:
        stmt = stmt.where(Mission.device_id == device_id)
        count_stmt = count_stmt.where(Mission.device_id == device_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Mission.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[MissionRead](
        items=[MissionRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=MissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual field survey mission",
)
def create_mission(
    payload: MissionCreate,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> MissionRead:
    _validate_mission_references(
        db,
        field_id=payload.field_id,
        device_id=payload.device_id,
        current_user=current_user,
    )

    mission = Mission(
        owner_id=current_user.id,
        operator_id=current_user.id,
        field_id=payload.field_id,
        device_id=payload.device_id,
        title=payload.title.strip(),
        description=payload.description,
        status=payload.status,
        operator_notes=payload.operator_notes,
        observations=[],
        metadata_json=dict(payload.metadata_json),
    )
    db.add(mission)
    db.flush()

    record_audit_event(
        db,
        action="mission.create",
        resource_type="mission",
        resource_id=mission.id,
        actor=current_user,
        request=request,
        metadata={"status": mission.status},
    )
    db.commit()
    db.refresh(mission)
    return MissionRead.model_validate(mission)


@router.get("/{mission_id}", response_model=MissionRead, summary="Retrieve mission by ID")
def get_mission(
    mission_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> MissionRead:
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError("Mission", str(mission_id))
    enforce_owner_or_admin(mission.owner_id, current_user)
    return MissionRead.model_validate(mission)


@router.patch("/{mission_id}", response_model=MissionRead, summary="Update mission details")
def update_mission(
    mission_id: uuid.UUID,
    payload: MissionUpdate,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> MissionRead:
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError("Mission", str(mission_id))
    enforce_owner_or_admin(mission.owner_id, current_user)

    if payload.unassign_field:
        mission.field_id = None
    elif payload.field_id is not None:
        _validate_mission_references(
            db, field_id=payload.field_id, device_id=None, current_user=current_user
        )
        mission.field_id = payload.field_id

    if payload.unassign_device:
        mission.device_id = None
    elif payload.device_id is not None:
        _validate_mission_references(
            db, field_id=None, device_id=payload.device_id, current_user=current_user
        )
        mission.device_id = payload.device_id

    if payload.title is not None:
        mission.title = payload.title.strip()
    if payload.description is not None:
        mission.description = payload.description
    if payload.operator_notes is not None:
        mission.operator_notes = payload.operator_notes
    if payload.metadata_json is not None:
        mission.metadata_json = dict(payload.metadata_json)

    record_audit_event(
        db,
        action="mission.update",
        resource_type="mission",
        resource_id=mission.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(mission)
    return MissionRead.model_validate(mission)


@router.post(
    "/{mission_id}/transition",
    response_model=MissionRead,
    summary="Transition mission status through validated lifecycle states",
)
def transition_mission(
    mission_id: uuid.UUID,
    payload: MissionTransitionRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> MissionRead:
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError("Mission", str(mission_id))
    enforce_owner_or_admin(mission.owner_id, current_user)

    current_status = mission.status
    target_status = payload.target_status
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ConflictError(
            f"Invalid mission transition from '{current_status}' to '{target_status}'.",
            details={"current_status": current_status, "allowed_targets": sorted(allowed)},
        )

    now = datetime.now(UTC)
    mission.status = target_status
    if target_status == "in_progress" and mission.started_at is None:
        mission.started_at = now
    elif target_status == "completed":
        if mission.started_at is None:
            mission.started_at = now
        mission.completed_at = now

    if payload.note and payload.note.strip():
        updated_obs = list(mission.observations or [])
        updated_obs.append(
            {
                "id": str(uuid.uuid4()),
                "author_id": str(current_user.id),
                "author_name": current_user.full_name,
                "note": f"[Status → {target_status}] {payload.note.strip()}",
                "recorded_at": now.isoformat(),
            }
        )
        mission.observations = updated_obs

    record_audit_event(
        db,
        action="mission.transition",
        resource_type="mission",
        resource_id=mission.id,
        actor=current_user,
        request=request,
        metadata={"from_status": current_status, "to_status": target_status},
    )
    from app.core.config import get_settings
    from app.services.alerts import evaluate_mission_status_event

    evaluate_mission_status_event(db, get_settings(), mission, current_status, target_status)
    db.commit()
    db.refresh(mission)
    return MissionRead.model_validate(mission)


@router.post(
    "/{mission_id}/observations",
    response_model=MissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Append a timestamped manual operator observation",
)
def add_mission_observation(
    mission_id: uuid.UUID,
    payload: MissionObservationCreate,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> MissionRead:
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError("Mission", str(mission_id))
    enforce_owner_or_admin(mission.owner_id, current_user)

    updated_obs = list(mission.observations or [])
    updated_obs.append(
        {
            "id": str(uuid.uuid4()),
            "author_id": str(current_user.id),
            "author_name": current_user.full_name,
            "note": payload.note.strip(),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    )
    mission.observations = updated_obs

    record_audit_event(
        db,
        action="mission.observation_add",
        resource_type="mission",
        resource_id=mission.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(mission)
    return MissionRead.model_validate(mission)


@router.delete(
    "/{mission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a mission",
)
def delete_mission(
    mission_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> Response:
    mission = db.get(Mission, mission_id)
    if mission is None:
        raise NotFoundError("Mission", str(mission_id))
    enforce_owner_or_admin(mission.owner_id, current_user)

    title = mission.title
    db.delete(mission)
    record_audit_event(
        db,
        action="mission.delete",
        resource_type="mission",
        resource_id=mission_id,
        actor=current_user,
        request=request,
        metadata={"title": title},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
