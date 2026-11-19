"""Secure Media Management: validated uploads, S3 presigning, authorized preview & download."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUserDep,
    DBSessionDep,
    OperatorWriterDep,
    SettingsDep,
    enforce_owner_or_admin,
)
from app.core.audit import record_audit_event
from app.core.exceptions import NotFoundError, PayloadTooLargeError
from app.models.field import Field
from app.models.media import MediaAsset
from app.models.mission import Mission
from app.schemas.common import PaginatedResponse
from app.schemas.domain import (
    MediaAssetRead,
    MediaDownloadUrlResponse,
    MediaPresignRequest,
    MediaPresignResponse,
)
from app.services.media_security import (
    sanitize_original_filename,
    validate_declared_upload,
    validate_uploaded_bytes,
)
from app.services.storage import StorageAdapter

router = APIRouter(prefix="/media", tags=["media"])

_UPLOAD_CHUNK_BYTES = 64 * 1024


def _validate_media_links(
    db: DBSessionDep,
    *,
    field_id: uuid.UUID | None,
    mission_id: uuid.UUID | None,
    current_user: CurrentUserDep,
) -> uuid.UUID | None:
    resolved_field_id = field_id
    if mission_id is not None:
        mission = db.get(Mission, mission_id)
        if mission is None:
            raise NotFoundError("Mission", str(mission_id))
        enforce_owner_or_admin(mission.owner_id, current_user)
        if resolved_field_id is None:
            resolved_field_id = mission.field_id

    if resolved_field_id is not None:
        field = db.get(Field, resolved_field_id)
        if field is None:
            raise NotFoundError("Field", str(resolved_field_id))
        enforce_owner_or_admin(field.owner_id, current_user)

    return resolved_field_id


@router.get("", response_model=PaginatedResponse[MediaAssetRead], summary="List media assets")
def list_media(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    q: str | None = Query(default=None, max_length=120),
    media_type: str | None = Query(default=None, max_length=16),
    field_id: uuid.UUID | None = Query(default=None),
    mission_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[MediaAssetRead]:
    stmt = select(MediaAsset)
    count_stmt = select(func.count()).select_from(MediaAsset)

    if current_user.role != "admin":
        stmt = stmt.where(MediaAsset.uploaded_by == current_user.id)
        count_stmt = count_stmt.where(MediaAsset.uploaded_by == current_user.id)

    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(MediaAsset.original_filename.ilike(pattern))
        count_stmt = count_stmt.where(MediaAsset.original_filename.ilike(pattern))

    if media_type:
        stmt = stmt.where(MediaAsset.media_type == media_type)
        count_stmt = count_stmt.where(MediaAsset.media_type == media_type)

    if field_id is not None:
        stmt = stmt.where(MediaAsset.field_id == field_id)
        count_stmt = count_stmt.where(MediaAsset.field_id == field_id)

    if mission_id is not None:
        stmt = stmt.where(MediaAsset.mission_id == mission_id)
        count_stmt = count_stmt.where(MediaAsset.mission_id == mission_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(MediaAsset.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[MediaAssetRead](
        items=[MediaAssetRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/upload",
    response_model=MediaAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image or video with magic-byte verification and size enforcement",
)
async def upload_media(
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    field_id: uuid.UUID | None = Form(default=None),
    mission_id: uuid.UUID | None = Form(default=None),
    notes: str | None = Form(default=None),
) -> MediaAssetRead:
    resolved_field_id = _validate_media_links(
        db,
        field_id=field_id,
        mission_id=mission_id,
        current_user=current_user,
    )

    media_type, _, _ = validate_declared_upload(
        filename=file.filename,
        declared_mime=file.content_type,
        byte_size=None,
        settings=settings,
    )
    max_bytes = (
        settings.max_image_upload_bytes
        if media_type == "image"
        else settings.max_video_upload_bytes
    )

    buffer = bytearray()
    hasher = hashlib.sha256()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        if len(buffer) + len(chunk) > max_bytes:
            raise PayloadTooLargeError(
                f"Upload exceeds maximum allowed size for {media_type} files ({max_bytes} bytes)."
            )
        buffer.extend(chunk)
        hasher.update(chunk)

    raw_bytes = bytes(buffer)
    validated = validate_uploaded_bytes(
        filename=file.filename,
        declared_mime=file.content_type,
        content=raw_bytes,
        settings=settings,
    )

    storage = StorageAdapter(settings)
    storage_key = storage.build_storage_key(str(current_user.id), validated.safe_filename)
    storage.put_bytes(storage_key, raw_bytes, validated.mime_type)

    asset = MediaAsset(
        mission_id=mission_id,
        field_id=resolved_field_id,
        uploaded_by=current_user.id,
        media_type=validated.media_type,
        upload_status="uploaded",
        storage_backend=settings.storage_backend,
        storage_key=storage_key,
        safe_filename=validated.safe_filename,
        original_filename=validated.sanitized_original_name,
        mime_type=validated.mime_type,
        byte_size=len(raw_bytes),
        sha256=hasher.hexdigest(),
        width_px=validated.width_px,
        height_px=validated.height_px,
        captured_at=datetime.now(UTC),
        geo_source="none",
        notes=(notes.strip()[:2000] if notes and notes.strip() else None),
    )

    try:
        db.add(asset)
        db.flush()
        record_audit_event(
            db,
            action="media.upload",
            resource_type="media_asset",
            resource_id=asset.id,
            actor=current_user,
            request=request,
            metadata={
                "mime_type": asset.mime_type,
                "byte_size": asset.byte_size,
                "storage_backend": asset.storage_backend,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_object(storage_key)
        raise

    db.refresh(asset)
    return MediaAssetRead.model_validate(asset)


@router.post(
    "/presign",
    response_model=MediaPresignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a short-lived private S3/MinIO presigned PUT URL (STORAGE_BACKEND=s3)",
)
def presign_media_upload(
    payload: MediaPresignRequest,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> MediaPresignResponse:
    resolved_field_id = _validate_media_links(
        db,
        field_id=payload.field_id,
        mission_id=payload.mission_id,
        current_user=current_user,
    )
    media_type, normalized_mime, canonical_ext = validate_declared_upload(
        filename=payload.filename,
        declared_mime=payload.mime_type,
        byte_size=payload.byte_size,
        settings=settings,
    )

    safe_filename = f"{uuid.uuid4().hex}{canonical_ext}"
    storage = StorageAdapter(settings)
    storage_key = storage.build_storage_key(str(current_user.id), safe_filename)
    presigned = storage.create_presigned_upload(
        storage_key=storage_key,
        content_type=normalized_mime,
        byte_size=payload.byte_size,
    )

    asset = MediaAsset(
        mission_id=payload.mission_id,
        field_id=resolved_field_id,
        uploaded_by=current_user.id,
        media_type=media_type,
        upload_status="pending_presign",
        storage_backend="s3",
        storage_key=storage_key,
        safe_filename=safe_filename,
        original_filename=sanitize_original_filename(payload.filename),
        mime_type=normalized_mime,
        byte_size=payload.byte_size,
        sha256=payload.sha256.lower(),
        geo_source="none",
        notes=payload.notes,
    )
    db.add(asset)
    db.flush()
    record_audit_event(
        db,
        action="media.presign",
        resource_type="media_asset",
        resource_id=asset.id,
        actor=current_user,
        request=request,
        metadata={"mime_type": normalized_mime, "byte_size": payload.byte_size},
    )
    db.commit()
    db.refresh(asset)

    return MediaPresignResponse(
        asset=MediaAssetRead.model_validate(asset),
        upload_url=presigned.url,
        method=presigned.method,
        headers=presigned.headers,
        expires_in_seconds=presigned.expires_in_seconds,
    )


@router.post(
    "/{media_id}/complete",
    response_model=MediaAssetRead,
    summary="Mark a presigned S3 upload as complete",
)
def complete_presigned_upload(
    media_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
) -> MediaAssetRead:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)
    asset.upload_status = "uploaded"
    record_audit_event(
        db,
        action="media.presign_complete",
        resource_type="media_asset",
        resource_id=asset.id,
        actor=current_user,
        request=request,
    )
    db.commit()
    db.refresh(asset)
    return MediaAssetRead.model_validate(asset)


@router.get("/{media_id}", response_model=MediaAssetRead, summary="Retrieve media metadata")
def get_media(
    media_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> MediaAssetRead:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)
    return MediaAssetRead.model_validate(asset)


@router.get(
    "/{media_id}/content",
    summary="Stream authorized media binary with strict non-executable security headers",
)
def stream_media_content(
    media_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    download: bool = Query(default=False),
) -> Response:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)

    storage = StorageAdapter(settings)
    content = storage.read_bytes(asset.storage_key)

    disposition_kind = "attachment" if download else "inline"
    safe_label = sanitize_original_filename(asset.original_filename)
    return Response(
        content=content,
        media_type=asset.mime_type,
        headers={
            "Content-Disposition": f'{disposition_kind}; filename="{safe_label}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get(
    "/{media_id}/download-url",
    response_model=MediaDownloadUrlResponse,
    summary="Return an authorized download/preview URL (presigned for S3, protected API path for local)",
)
def get_media_download_url(
    media_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    download: bool = Query(default=False),
) -> MediaDownloadUrlResponse:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)

    safe_label = sanitize_original_filename(asset.original_filename)
    if asset.storage_backend == "s3" and settings.storage_backend == "s3":
        storage = StorageAdapter(settings)
        url, expires = storage.create_presigned_download_url(
            storage_key=asset.storage_key,
            filename=safe_label,
            as_attachment=download,
        )
        return MediaDownloadUrlResponse(
            media_id=asset.id,
            storage_backend="s3",
            url=url,
            expires_in_seconds=expires,
            filename=safe_label,
        )

    suffix = "?download=true" if download else ""
    return MediaDownloadUrlResponse(
        media_id=asset.id,
        storage_backend=asset.storage_backend,
        url=f"{settings.api_prefix}/media/{asset.id}/content{suffix}",
        expires_in_seconds=None,
        filename=safe_label,
    )


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a media asset and its stored binary",
)
def delete_media(
    media_id: uuid.UUID,
    request: Request,
    current_user: OperatorWriterDep,
    db: DBSessionDep,
    settings: SettingsDep,
) -> Response:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError("Media asset", str(media_id))
    enforce_owner_or_admin(asset.uploaded_by, current_user)

    storage_key = asset.storage_key
    original_filename = asset.original_filename
    db.delete(asset)
    record_audit_event(
        db,
        action="media.delete",
        resource_type="media_asset",
        resource_id=media_id,
        actor=current_user,
        request=request,
        metadata={"original_filename": original_filename},
    )
    db.commit()

    StorageAdapter(settings).delete_object(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
