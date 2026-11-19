"""Phase 3 AgroVision AI Engine endpoints: model registry, datasets, async jobs, annotated media, review, and export."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Path, Query, Request, Response, status
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentUserDep,
    DBSessionDep,
    FieldWriterDep,
    OperatorWriterDep,
    SettingsDep,
    enforce_owner_or_admin,
)
from app.core.audit import record_audit_event
from app.core.exceptions import (
    ConflictError,
    FeatureNotEnabledError,
    NotFoundError,
    ValidationAppError,
)
from app.models.detection import DetectionItem, DetectionJob, RegisteredDataset
from app.models.media import MediaAsset
from app.schemas.common import PaginatedResponse
from app.schemas.detection import (
    DatasetRead,
    DatasetRegisterRequest,
    DetectionItemRead,
    DetectionItemReviewRequest,
    DetectionJobCreateRequest,
    DetectionJobDetailRead,
    DetectionJobRead,
    ModelRegistryItemSchema,
)
from app.schemas.domain import MediaAssetRead
from app.services.media_security import sanitize_original_filename
from app.services.storage import StorageAdapter
from app.services.vision import (
    build_annotated_key,
    dispatch_detection_job,
    get_model_catalog_schemas,
    recompute_job_review_summary,
    resolve_available_model,
)

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get(
    "/models",
    response_model=list[ModelRegistryItemSchema],
    summary="List registered general and specialized agricultural detection models",
)
def list_models(_current_user: CurrentUserDep) -> list[ModelRegistryItemSchema]:
    return get_model_catalog_schemas()


@router.get(
    "/datasets",
    response_model=PaginatedResponse[DatasetRead],
    summary="List registered agricultural evaluation datasets",
)
def list_datasets(
    _current_user: CurrentUserDep,
    db: DBSessionDep,
    detection_mode: str | None = Query(default=None, max_length=48),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[DatasetRead]:
    stmt = select(RegisteredDataset)
    count_stmt = select(func.count()).select_from(RegisteredDataset)
    if detection_mode:
        stmt = stmt.where(RegisteredDataset.detection_mode == detection_mode)
        count_stmt = count_stmt.where(RegisteredDataset.detection_mode == detection_mode)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(RegisteredDataset.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[DatasetRead](
        items=[DatasetRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/datasets",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a documented agricultural dataset with train/val/test counts and mAP metrics",
)
def register_dataset(
    payload: DatasetRegisterRequest,
    request: Request,
    current_user: FieldWriterDep,
    db: DBSessionDep,
) -> DatasetRead:
    dataset = RegisteredDataset(
        owner_id=current_user.id,
        name=payload.name.strip(),
        version=payload.version.strip(),
        detection_mode=payload.detection_mode,
        classes_json=payload.classes,
        train_count=payload.train_count,
        val_count=payload.val_count,
        test_count=payload.test_count,
        metrics_json=payload.metrics.model_dump(),
        notes=payload.notes,
    )
    db.add(dataset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"A dataset named '{payload.name}' is already registered.") from exc

    record_audit_event(
        db,
        action="dataset.register",
        resource_type="registered_dataset",
        resource_id=dataset.id,
        actor=current_user,
        request=request,
        metadata={
            "name": dataset.name,
            "detection_mode": dataset.detection_mode,
            "map50": payload.metrics.map50,
        },
    )
    db.commit()
    db.refresh(dataset)
    return DatasetRead.model_validate(dataset)


@router.post(
    "/jobs",
    response_model=DetectionJobDetailRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and execute an image or sampled-video AI detection job",
)
def create_detection_job(
    payload: DetectionJobCreateRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> DetectionJobDetailRead:
    if not settings.ai_inference_enabled:
        raise FeatureNotEnabledError(
            feature="AgroVision AI inference",
            target_phase="Phase 3",
            reason="Set AI_INFERENCE_ENABLED=true to allow detection jobs.",
        )

    asset = db.get(MediaAsset, payload.media_asset_id)
    if asset is None:
        raise NotFoundError("Media asset", str(payload.media_asset_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)

    if asset.upload_status != "uploaded":
        raise ValidationAppError(
            f"Media asset '{asset.original_filename}' is in state '{asset.upload_status}' and cannot be analyzed yet."
        )

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
        frame_sample_interval_ms=(
            payload.frame_sample_interval_ms if asset.media_type == "video" else None
        ),
        max_frames=(payload.max_frames if asset.media_type == "video" else None),
        summary_json={},
    )
    db.add(job)
    db.flush()

    record_audit_event(
        db,
        action="detection_job.create",
        resource_type="detection_job",
        resource_id=job.id,
        actor=current_user,
        request=request,
        metadata={
            "media_asset_id": str(asset.id),
            "media_type": asset.media_type,
            "model_id": model_entry.model_id,
            "confidence_threshold": payload.confidence_threshold,
        },
    )
    db.commit()

    dispatch_detection_job(
        job_id=job.id,
        db=db,
        settings=settings,
        run_async=payload.run_async,
    )

    db.refresh(job)
    items = db.scalars(
        select(DetectionItem)
        .where(DetectionItem.job_id == job.id)
        .order_by(DetectionItem.frame_index.asc(), DetectionItem.confidence.desc())
    ).all()

    return DetectionJobDetailRead(
        **DetectionJobRead.model_validate(job).model_dump(),
        items=[DetectionItemRead.model_validate(item) for item in items],
        media_asset=MediaAssetRead.model_validate(asset),
    )


def _query_detection_jobs(
    *,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None,
    status_filter: str | None,
    model_id: str | None,
    detection_mode: str | None,
    media_type: str | None,
    field_id: uuid.UUID | None,
    mission_id: uuid.UUID | None,
    review_status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    sort_by: Literal["newest", "oldest", "duration_desc"],
    limit: int,
    offset: int,
) -> PaginatedResponse[DetectionJobRead]:
    stmt = select(DetectionJob).outerjoin(
        MediaAsset, DetectionJob.media_asset_id == MediaAsset.id
    )
    count_stmt = (
        select(func.count())
        .select_from(DetectionJob)
        .outerjoin(MediaAsset, DetectionJob.media_asset_id == MediaAsset.id)
    )

    if current_user.role != "admin":
        owner_cond = or_(
            DetectionJob.owner_id == current_user.id,
            MediaAsset.uploaded_by == current_user.id,
        )
        stmt = stmt.where(owner_cond)
        count_stmt = count_stmt.where(owner_cond)

    if q:
        pattern = f"%{q.strip()}%"
        cond = or_(
            DetectionJob.model_name.ilike(pattern),
            DetectionJob.model_id.ilike(pattern),
            DetectionJob.dataset_scope.ilike(pattern),
            MediaAsset.original_filename.ilike(pattern),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if status_filter:
        stmt = stmt.where(DetectionJob.status == status_filter)
        count_stmt = count_stmt.where(DetectionJob.status == status_filter)

    if model_id:
        stmt = stmt.where(DetectionJob.model_id == model_id)
        count_stmt = count_stmt.where(DetectionJob.model_id == model_id)

    if detection_mode:
        stmt = stmt.where(DetectionJob.detection_mode == detection_mode)
        count_stmt = count_stmt.where(DetectionJob.detection_mode == detection_mode)

    if media_type:
        stmt = stmt.where(DetectionJob.media_type == media_type)
        count_stmt = count_stmt.where(DetectionJob.media_type == media_type)

    if field_id is not None:
        stmt = stmt.where(DetectionJob.field_id == field_id)
        count_stmt = count_stmt.where(DetectionJob.field_id == field_id)

    if mission_id is not None:
        stmt = stmt.where(DetectionJob.mission_id == mission_id)
        count_stmt = count_stmt.where(DetectionJob.mission_id == mission_id)

    if review_status:
        subq = exists().where(
            DetectionItem.job_id == DetectionJob.id,
            DetectionItem.review_status == review_status,
        )
        stmt = stmt.where(subq)
        count_stmt = count_stmt.where(subq)

    if date_from is not None:
        stmt = stmt.where(DetectionJob.created_at >= date_from)
        count_stmt = count_stmt.where(DetectionJob.created_at >= date_from)

    if date_to is not None:
        stmt = stmt.where(DetectionJob.created_at <= date_to)
        count_stmt = count_stmt.where(DetectionJob.created_at <= date_to)

    if sort_by == "oldest":
        stmt = stmt.order_by(DetectionJob.created_at.asc())
    elif sort_by == "duration_desc":
        stmt = stmt.order_by(
            DetectionJob.inference_ms.desc().nulls_last(), DetectionJob.created_at.desc()
        )
    else:
        stmt = stmt.order_by(DetectionJob.created_at.desc())

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return PaginatedResponse[DetectionJobRead](
        items=[DetectionJobRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "",
    response_model=PaginatedResponse[DetectionJobRead],
    summary="List AI detection jobs with search, filtering, and sorting",
)
@router.get(
    "/jobs",
    response_model=PaginatedResponse[DetectionJobRead],
    summary="List AI detection jobs with search, filtering, and sorting",
)
def list_detection_jobs(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    model_id: str | None = Query(default=None, max_length=80),
    detection_mode: str | None = Query(default=None, max_length=48),
    media_type: str | None = Query(default=None, max_length=16),
    field_id: uuid.UUID | None = Query(default=None),
    mission_id: uuid.UUID | None = Query(default=None),
    review_status: str | None = Query(default=None, max_length=32),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: Literal["newest", "oldest", "duration_desc"] = Query(default="newest"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[DetectionJobRead]:
    return _query_detection_jobs(
        current_user=current_user,
        db=db,
        q=q,
        status_filter=status_filter,
        model_id=model_id,
        detection_mode=detection_mode,
        media_type=media_type,
        field_id=field_id,
        mission_id=mission_id,
        review_status=review_status,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


def _load_authorized_job(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> tuple[DetectionJob, MediaAsset | None]:
    job = db.get(DetectionJob, job_id)
    if job is None:
        raise NotFoundError("Detection job", str(job_id))
    asset = db.get(MediaAsset, job.media_asset_id)
    owner_id = job.owner_id or (asset.uploaded_by if asset else None)
    enforce_owner_or_admin(owner_id, current_user)
    return job, asset


@router.get(
    "/jobs/{job_id}",
    response_model=DetectionJobDetailRead,
    summary="Retrieve detection job status, model provenance, and all detected bounding boxes",
)
def get_detection_job(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> DetectionJobDetailRead:
    job, asset = _load_authorized_job(job_id, current_user, db)
    items = db.scalars(
        select(DetectionItem)
        .where(DetectionItem.job_id == job.id)
        .order_by(DetectionItem.frame_index.asc(), DetectionItem.confidence.desc())
    ).all()
    return DetectionJobDetailRead(
        **DetectionJobRead.model_validate(job).model_dump(),
        items=[DetectionItemRead.model_validate(item) for item in items],
        media_asset=MediaAssetRead.model_validate(asset) if asset else None,
    )


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=DetectionJobRead,
    summary="Cancel a queued or processing detection job",
)
def cancel_detection_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> DetectionJobRead:
    job, _ = _load_authorized_job(job_id, current_user, db)
    if job.status in {"completed", "failed", "cancelled"}:
        raise ConflictError(f"Cannot cancel a job that is already '{job.status}'.")

    job.status = "cancelled"
    job.error_message = "Analysis cancelled by operator."
    job.completed_at = datetime.now(UTC)
    record_audit_event(
        db,
        action="detection_job.cancel",
        resource_type="detection_job",
        resource_id=job.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(job)
    return DetectionJobRead.model_validate(job)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=DetectionJobDetailRead,
    summary="Safely retry a failed or cancelled detection job",
)
def retry_detection_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
    run_async: bool = Query(default=True),
) -> DetectionJobDetailRead:
    job, asset = _load_authorized_job(job_id, current_user, db)
    if job.status not in {"failed", "cancelled"}:
        raise ConflictError(
            f"Only failed or cancelled jobs can be retried (current status: '{job.status}')."
        )

    resolve_available_model(job.model_id)

    db.execute(delete(DetectionItem).where(DetectionItem.job_id == job.id))
    job.status = "queued"
    job.progress_percent = 0
    job.error_message = None
    job.started_at = None
    job.completed_at = None

    summary = dict(job.summary_json or {})
    summary["retry_count"] = int(summary.get("retry_count", 0)) + 1
    job.summary_json = summary

    record_audit_event(
        db,
        action="detection_job.retry",
        resource_type="detection_job",
        resource_id=job.id,
        actor=current_user,
        request=request,
        metadata={"retry_count": summary["retry_count"]},
    )
    db.commit()

    dispatch_detection_job(
        job_id=job.id,
        db=db,
        settings=settings,
        run_async=run_async,
    )
    db.refresh(job)
    items = db.scalars(
        select(DetectionItem)
        .where(DetectionItem.job_id == job.id)
        .order_by(DetectionItem.frame_index.asc(), DetectionItem.confidence.desc())
    ).all()
    return DetectionJobDetailRead(
        **DetectionJobRead.model_validate(job).model_dump(),
        items=[DetectionItemRead.model_validate(item) for item in items],
        media_asset=MediaAssetRead.model_validate(asset) if asset else None,
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a detection job and its annotated media artifacts",
)
def delete_detection_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> Response:
    job, _ = _load_authorized_job(job_id, current_user, db)
    annotated_key = job.annotated_storage_key
    item_frame_keys = [
        k
        for k in db.scalars(
            select(DetectionItem.annotated_frame_storage_key).where(
                DetectionItem.job_id == job.id
            )
        ).all()
        if k
    ]

    db.delete(job)
    record_audit_event(
        db,
        action="detection_job.delete",
        resource_type="detection_job",
        resource_id=job_id,
        actor=current_user,
        request=request,
    )
    db.commit()

    storage = StorageAdapter(settings)
    for key in {annotated_key, *item_frame_keys}:
        if key:
            storage.delete_object(key)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/jobs/{job_id}/annotated",
    summary="Stream or download the authorized annotated detection image",
)
def stream_annotated_result(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    download: bool = Query(default=False),
) -> Response:
    job, asset = _load_authorized_job(job_id, current_user, db)
    if not job.annotated_storage_key:
        raise NotFoundError("Annotated result image", str(job_id))

    content = StorageAdapter(settings).read_bytes(job.annotated_storage_key)
    base_name = sanitize_original_filename(
        asset.original_filename if asset else f"job_{job_id}.jpg"
    )
    out_filename = f"annotated_{base_name}.jpg"
    disposition_kind = "attachment" if download else "inline"

    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'{disposition_kind}; filename="{out_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get(
    "/jobs/{job_id}/frames/{frame_index}/annotated",
    summary="Stream an authorized annotated video frame preview by sampled frame index",
)
def stream_annotated_video_frame(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    frame_index: int = Path(ge=0, le=500),
) -> Response:
    job, asset = _load_authorized_job(job_id, current_user, db)
    sampled = int(job.total_frames_sampled or 0)
    if job.media_type != "video" or frame_index >= sampled:
        raise NotFoundError("Annotated video frame", f"{job_id}:{frame_index}")
    owner_str = str(job.owner_id or (asset.uploaded_by if asset else "system"))
    frame_key = build_annotated_key(owner_str, str(job.id), f"frame_{frame_index:04d}.jpg")
    content = StorageAdapter(settings).read_bytes(frame_key)
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="frame_{frame_index:04d}.jpg"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.patch(
    "/items/{item_id}/review",
    response_model=DetectionItemRead,
    summary="Review a detection item while preserving original machine predictions",
)
def review_detection_item(
    item_id: uuid.UUID,
    payload: DetectionItemReviewRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> DetectionItemRead:
    item = db.get(DetectionItem, item_id)
    if item is None:
        raise NotFoundError("Detection item", str(item_id))

    job, _ = _load_authorized_job(item.job_id, current_user, db)

    # Preserve original machine prediction immutably on first review
    if item.original_label is None:
        item.original_label = item.label
    if item.original_confidence is None:
        item.original_confidence = item.confidence

    item.review_status = payload.review_status
    item.reviewer_id = current_user.id
    item.reviewed_at = datetime.now(UTC)
    if payload.reviewer_notes is not None:
        item.reviewer_notes = payload.reviewer_notes.strip() or None
    if payload.corrected_label and payload.corrected_label.strip():
        item.label = payload.corrected_label.strip()

    recompute_job_review_summary(db, job)

    record_audit_event(
        db,
        action="detection_item.review",
        resource_type="detection_item",
        resource_id=item.id,
        actor=current_user,
        request=request,
        metadata={
            "job_id": str(job.id),
            "review_status": item.review_status,
            "original_label": item.original_label,
            "current_label": item.label,
        },
    )
    db.commit()
    if item.review_status == "confirmed":
        from app.core.config import get_settings
        from app.services.alerts import evaluate_human_confirmed_event

        evaluate_human_confirmed_event(db, get_settings(), item.id)
        db.commit()
    db.refresh(item)
    return DetectionItemRead.model_validate(item)


@router.get(
    "/jobs/{job_id}/export",
    summary="Export complete detection job provenance, machine predictions, and human review as JSON",
)
def export_detection_job_json(
    job_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> Response:
    job, asset = _load_authorized_job(job_id, current_user, db)
    items = db.scalars(
        select(DetectionItem)
        .where(DetectionItem.job_id == job.id)
        .order_by(DetectionItem.frame_index.asc(), DetectionItem.confidence.desc())
    ).all()

    report: dict[str, Any] = {
        "schema_version": "agrodrone.agrovision.v3",
        "exported_at": datetime.now(UTC).isoformat(),
        "job": {
            "id": str(job.id),
            "status": job.status,
            "detection_mode": job.detection_mode,
            "media_type": job.media_type,
            "confidence_threshold": job.confidence_threshold,
            "inference_ms": job.inference_ms,
            "device_used": job.device_used,
            "frame_sample_interval_ms": job.frame_sample_interval_ms,
            "total_frames_sampled": job.total_frames_sampled,
            "video_duration_ms": job.video_duration_ms,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "model_provenance": {
            "model_id": job.model_id,
            "model_name": job.model_name,
            "model_version": job.model_version,
            "model_checksum_sha256": job.model_checksum,
            "dataset_scope": job.dataset_scope,
        },
        "media_asset": (
            {
                "id": str(asset.id),
                "original_filename": asset.original_filename,
                "mime_type": asset.mime_type,
                "byte_size": asset.byte_size,
                "sha256": asset.sha256,
                "width_px": asset.width_px,
                "height_px": asset.height_px,
            }
            if asset
            else None
        ),
        "summary": job.summary_json,
        "detections": [
            {
                "id": str(item.id),
                "frame_index": item.frame_index,
                "timestamp_ms": item.timestamp_ms,
                "bounding_box": {
                    "x1": item.bbox_x1,
                    "y1": item.bbox_y1,
                    "x2": item.bbox_x2,
                    "y2": item.bbox_y2,
                },
                "machine_prediction": {
                    "class_id": item.class_id,
                    "label": item.original_label or item.label,
                    "confidence": (
                        item.original_confidence
                        if item.original_confidence is not None
                        else item.confidence
                    ),
                },
                "human_review": {
                    "review_status": item.review_status,
                    "verified_label": item.label,
                    "reviewer_id": str(item.reviewer_id) if item.reviewer_id else None,
                    "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                    "reviewer_notes": item.reviewer_notes,
                },
            }
            for item in items
        ],
    }

    payload_bytes = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    return Response(
        content=payload_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="agrovision_job_{job.id}.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
