"""AgroVision AI orchestration: model catalog, durable job claiming, execution, recovery, and honesty policy."""

from __future__ import annotations

import contextlib
import hashlib
import uuid
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from agrovision_worker.engine import (
    InferenceEngineError,
    RawDetectionBox,
    analyze_image_bytes,
    analyze_video_bytes,
    model_runtime_cache,
)
from agrovision_worker.registry import (
    GENERAL_MODEL_ID,
    ModelRegistryEntry,
    build_model_registry,
    with_classes,
)
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.models.detection import DetectionItem, DetectionJob
from app.models.media import MediaAsset
from app.schemas.detection import ModelEvaluationSchema, ModelRegistryItemSchema
from app.schemas.system import AICapabilityPolicy
from app.services.storage import StorageAdapter

logger = get_logger(__name__)

_worker_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agrovision-worker")

# Deterministic predictor overrides used only by unit tests (never set in runtime code paths).
_test_image_predictor: Callable[[np.ndarray, float], list[RawDetectionBox]] | None = None
_test_video_predictor: Callable[[np.ndarray, float, int, int], list[RawDetectionBox]] | None = None


def set_test_predictors(
    image_predictor: Callable[[np.ndarray, float], list[RawDetectionBox]] | None = None,
    video_predictor: Callable[[np.ndarray, float, int, int], list[RawDetectionBox]] | None = None,
) -> None:
    global _test_image_predictor, _test_video_predictor
    _test_image_predictor = image_predictor
    _test_video_predictor = video_predictor


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------


def _weights_dir() -> Path | None:
    configured = get_settings().ai_weights_dir.strip()
    return Path(configured) if configured else None


def get_model_catalog() -> list[ModelRegistryEntry]:
    """Return registry entries; the general model's class list is read from the real checkpoint."""
    entries = build_model_registry(weights_dir=_weights_dir())
    resolved: list[ModelRegistryEntry] = []
    for entry in entries:
        if entry.model_id == GENERAL_MODEL_ID and entry.status == "available":
            names = model_runtime_cache.get_loaded_class_names(entry)
            if names:
                entry = with_classes(entry, names)
        resolved.append(entry)
    return resolved


def get_model_catalog_schemas() -> list[ModelRegistryItemSchema]:
    items: list[ModelRegistryItemSchema] = []
    for entry in get_model_catalog():
        items.append(
            ModelRegistryItemSchema(
                model_id=entry.model_id,
                name=entry.name,
                version=entry.version,
                detection_mode=entry.detection_mode,
                architecture=entry.architecture,
                license_spdx=entry.license_spdx,
                dataset_scope=entry.dataset_scope,
                status=entry.status,
                status_reason=entry.status_reason,
                weights_filename=entry.weights_filename,
                expected_sha256=entry.expected_sha256,
                actual_sha256=entry.actual_sha256,
                supported_classes=entry.supported_classes,
                total_class_count=entry.total_class_count,
                default_confidence=entry.default_confidence,
                is_specialized_agricultural=entry.is_specialized_agricultural,
                honesty_disclaimer=entry.honesty_disclaimer,
                evaluation=(
                    ModelEvaluationSchema(**asdict(entry.evaluation)) if entry.evaluation else None
                ),
                requirements_for_activation=entry.requirements_for_activation,
            )
        )
    return items


def resolve_available_model(model_id: str) -> ModelRegistryEntry:
    entry = next((m for m in get_model_catalog() if m.model_id == model_id), None)
    if entry is None:
        raise ValidationAppError(
            f"Unknown model_id '{model_id}'. See GET /api/v1/detections/models.",
            details={"model_id": model_id, "status": "unknown"},
        )
    if entry.status != "available":
        raise ValidationAppError(
            f"Model Not Available: '{entry.name}'. {entry.status_reason}",
            details={
                "model_id": entry.model_id,
                "detection_mode": entry.detection_mode,
                "status": entry.status,
                "requirements_for_activation": entry.requirements_for_activation,
            },
        )
    return entry


def get_ai_capability_policy(settings: Settings) -> AICapabilityPolicy:
    catalog = get_model_catalog()
    general = next((m for m in catalog if m.model_id == GENERAL_MODEL_ID), None)
    validated = general.supported_classes if (general and general.status == "available") else []
    return AICapabilityPolicy(
        inference_enabled=settings.ai_inference_enabled,
        active_model_profile=settings.ai_model_profile,
        first_working_workflow=(
            "Phase 3: asynchronous image and sampled-frame video analysis with Ultralytics YOLOv8n "
            "(PyTorch, OpenCV, Pillow), SHA-256 model provenance, annotated outputs and human review."
        ),
        model_honesty_notice=(
            "Generic pre-trained YOLO weights (COCO) are used only for General Object Detection of "
            "their 80 baseline classes. They CANNOT reliably detect snakes, hedgehogs, small insects, "
            "or specific crop diseases without curated domain imagery, train/val/test separation and "
            "verified precision/recall/mAP evaluation."
        ),
        validated_target_classes=validated,
        requires_custom_training_for=[
            "Snakes, hedgehogs and rodents (agrovision-wildlife-v1 — Model Not Available)",
            "Small agricultural insects and pests (agrovision-pest-v1 — Model Not Available)",
            "Specific crop diseases (agrovision-disease-v1 — Model Not Available; OV2640 is RGB-only)",
            "Regional weed species differentiation",
        ],
    )


def build_annotated_key(owner_id: str, job_id: str, filename: str = "annotated.jpg") -> str:
    return f"detections/{owner_id}/{job_id}/{filename}"


def recompute_job_review_summary(db: Session, job: DetectionJob) -> dict[str, Any]:
    """Recompute human review counts; machine predictions are never modified here."""
    items = db.scalars(select(DetectionItem).where(DetectionItem.job_id == job.id)).all()
    counts = Counter(item.review_status for item in items)
    summary = dict(job.summary_json or {})
    summary["review_counts"] = {
        key: counts.get(key, 0) for key in ("unreviewed", "confirmed", "rejected", "uncertain")
    }
    job.summary_json = summary
    return summary


# ---------------------------------------------------------------------------
# Durable job claiming & execution
# ---------------------------------------------------------------------------


def claim_job(db: Session, job_id: uuid.UUID) -> bool:
    """Atomically transition queued -> processing (compare-and-set). Portable to SQLite & PostgreSQL."""
    result = db.execute(
        update(DetectionJob)
        .where(DetectionJob.id == job_id, DetectionJob.status == "queued")
        .values(
            status="processing",
            progress_percent=5,
            started_at=datetime.now(UTC),
            error_message=None,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return (result.rowcount or 0) == 1


def _bump_attempts(job: DetectionJob) -> int:
    summary = dict(job.summary_json or {})
    summary["attempts"] = int(summary.get("attempts", 0)) + 1
    job.summary_json = summary
    return summary["attempts"]


def _persist_items(db: Session, job: DetectionJob, boxes: list[RawDetectionBox], key_for: Callable[[int], str]) -> None:
    db.execute(delete(DetectionItem).where(DetectionItem.job_id == job.id))
    for box in boxes:
        db.add(
            DetectionItem(
                job_id=job.id,
                class_id=box.class_id,
                label=box.label,
                confidence=box.confidence,
                original_label=box.label,
                original_confidence=box.confidence,
                bbox_x1=box.bbox_x1,
                bbox_y1=box.bbox_y1,
                bbox_x2=box.bbox_x2,
                bbox_y2=box.bbox_y2,
                frame_index=box.frame_index,
                timestamp_ms=box.timestamp_ms,
                annotated_frame_storage_key=key_for(box.frame_index),
                review_status="unreviewed",
            )
        )


def _fail(db: Session, job_id: uuid.UUID, message: str, *, cancelled: bool = False) -> None:
    db.rollback()
    job = db.get(DetectionJob, job_id)
    if job is None:
        return
    db.refresh(job)
    if cancelled or job.status == "cancelled":
        job.status = "cancelled"
        job.error_message = "Analysis cancelled by operator."
    else:
        job.status = "failed"
        job.error_message = message[:2000]
    job.completed_at = datetime.now(UTC)
    db.commit()
    if job.status == "failed":
        from app.core.config import get_settings
        from app.services.alerts import evaluate_detection_job_event

        evaluate_detection_job_event(db, get_settings(), job.id)
        db.commit()


def execute_detection_job_in_session(job_id: uuid.UUID, db: Session, settings: Settings) -> None:
    """Claim and execute one DetectionJob. Safe to call repeatedly: only a queued job is executed."""
    if not claim_job(db, job_id):
        return

    job = db.get(DetectionJob, job_id)
    if job is None:
        return
    db.refresh(job)
    _bump_attempts(job)
    db.commit()

    asset = db.get(MediaAsset, job.media_asset_id)
    if asset is None:
        _fail(db, job_id, "[MEDIA_MISSING] Associated media asset no longer exists.")
        return

    model_entry = next((m for m in get_model_catalog() if m.model_id == job.model_id), None)
    if model_entry is None or model_entry.status != "available":
        reason = model_entry.status_reason if model_entry else f"Model '{job.model_id}' is not registered."
        _fail(db, job_id, f"[MODEL_NOT_AVAILABLE] {reason}")
        return

    storage = StorageAdapter(settings)
    owner_str = str(job.owner_id or asset.uploaded_by or "system")
    job_str = str(job.id)
    written_keys: list[str] = []

    try:
        raw_bytes = storage.read_bytes(asset.storage_key)
        if hashlib.sha256(raw_bytes).hexdigest() != asset.sha256:
            raise InferenceEngineError(
                "MEDIA_INTEGRITY_FAILED",
                "Stored media SHA-256 does not match the digest recorded at upload.",
            )

        if asset.media_type == "image":
            result = analyze_image_bytes(
                raw_bytes,
                model_entry=model_entry,
                confidence_threshold=job.confidence_threshold,
                requested_device=settings.ai_device,
                custom_predictor=_test_image_predictor,
            )
            db.refresh(job)
            if job.status == "cancelled":
                return

            annotated_key = build_annotated_key(owner_str, job_str, "annotated.jpg")
            storage.put_bytes(annotated_key, result.annotated_jpeg_bytes, "image/jpeg")
            written_keys.append(annotated_key)
            _persist_items(db, job, result.detections, lambda _i: annotated_key)

            n = len(result.detections)
            job.model_checksum = result.model_checksum
            job.device_used = result.device_used
            job.inference_ms = result.inference_ms
            job.total_frames_sampled = 1
            job.annotated_storage_key = annotated_key
            job.progress_percent = 100
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.summary_json = {
                **(job.summary_json or {}),
                "analysis_type": "still_image",
                "total_detections": n,
                "class_counts": result.class_counts,
                "average_confidence": (
                    round(sum(d.confidence for d in result.detections) / n, 4) if n else None
                ),
                "width_px": result.width_px,
                "height_px": result.height_px,
                "review_counts": {"unreviewed": n, "confirmed": 0, "rejected": 0, "uncertain": 0},
            }
            db.commit()
            from app.services.alerts import evaluate_detection_job_event

            evaluate_detection_job_event(db, settings, job.id)
            db.commit()
            logger.info("detection_job_completed", job_id=job_str, media_type="image", detections=n, inference_ms=result.inference_ms)
            return

        suffix = Path(asset.safe_filename or asset.original_filename or "clip.mp4").suffix or ".mp4"
        interval = job.frame_sample_interval_ms or settings.default_frame_sample_interval_ms
        max_frames = min(job.max_frames or 20, settings.max_video_sampled_frames)

        def _on_progress(pct: int) -> None:
            db.execute(
                update(DetectionJob)
                .where(DetectionJob.id == job.id, DetectionJob.status == "processing")
                .values(progress_percent=pct)
                .execution_options(synchronize_session=False)
            )
            db.commit()

        def _is_cancelled() -> bool:
            status = db.scalar(select(DetectionJob.status).where(DetectionJob.id == job.id))
            return status == "cancelled"

        vid = analyze_video_bytes(
            raw_bytes,
            file_suffix=suffix,
            model_entry=model_entry,
            confidence_threshold=job.confidence_threshold,
            requested_device=settings.ai_device,
            frame_sample_interval_ms=interval,
            max_frames=max_frames,
            max_duration_seconds=settings.max_video_duration_seconds,
            progress_callback=_on_progress,
            cancel_check=_is_cancelled,
            custom_predictor=_test_video_predictor,
        )
        db.refresh(job)
        if job.status == "cancelled":
            return

        primary_key = build_annotated_key(owner_str, job_str, "annotated.jpg")
        storage.put_bytes(primary_key, vid.primary_annotated_jpeg_bytes, "image/jpeg")
        written_keys.append(primary_key)

        frame_keys: dict[int, str] = {}
        frames_meta: list[dict[str, Any]] = []
        for frame in vid.sampled_frames:
            key = build_annotated_key(owner_str, job_str, f"frame_{frame.sampled_index:04d}.jpg")
            storage.put_bytes(key, frame.annotated_jpeg_bytes, "image/jpeg")
            written_keys.append(key)
            frame_keys[frame.sampled_index] = key
            frames_meta.append(
                {
                    "frame_index": frame.sampled_index,
                    "raw_frame_index": frame.raw_frame_index,
                    "timestamp_ms": frame.timestamp_ms,
                    "detection_count": len(frame.detections),
                }
            )

        _persist_items(db, job, vid.detections, lambda i: frame_keys.get(i, primary_key))

        n = len(vid.detections)
        job.model_checksum = vid.model_checksum
        job.device_used = vid.device_used
        job.inference_ms = vid.inference_ms
        job.total_frames_sampled = vid.total_frames_sampled
        job.video_duration_ms = vid.video_duration_ms
        job.annotated_storage_key = primary_key
        job.progress_percent = 100
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.summary_json = {
            **(job.summary_json or {}),
            "analysis_type": "sampled_video",
            "sampling_mode": "sampled_frames_only",
            "sampling_notice": (
                f"Analyzed {vid.total_frames_sampled} sampled frames at {vid.frame_sample_interval_ms} ms "
                f"intervals out of {vid.total_video_frames} total frames. This is NOT full-frame analysis."
            ),
            "total_detections": n,
            "class_counts": vid.class_counts,
            "average_confidence": round(sum(d.confidence for d in vid.detections) / n, 4) if n else None,
            "width_px": vid.width_px,
            "height_px": vid.height_px,
            "total_video_frames": vid.total_video_frames,
            "total_frames_sampled": vid.total_frames_sampled,
            "frame_sample_interval_ms": vid.frame_sample_interval_ms,
            "video_duration_ms": vid.video_duration_ms,
            "sampled_frames": frames_meta,
            "review_counts": {"unreviewed": n, "confirmed": 0, "rejected": 0, "uncertain": 0},
        }
        db.commit()
        from app.services.alerts import evaluate_detection_job_event

        evaluate_detection_job_event(db, settings, job.id)
        db.commit()
        logger.info("detection_job_completed", job_id=job_str, media_type="video", frames=vid.total_frames_sampled, detections=n, inference_ms=vid.inference_ms)
    except InferenceEngineError as exc:
        for key in written_keys:
            storage.delete_object(key)
        _fail(db, job_id, f"[{exc.code}] {exc.message}", cancelled=exc.code == "JOB_CANCELLED")
        logger.warning("detection_job_failed", job_id=job_str, code=exc.code)
    except Exception as exc:  # noqa: BLE001 - worker must never crash the process
        for key in written_keys:
            with contextlib.suppress(Exception):
                storage.delete_object(key)
        _fail(db, job_id, f"[WORKER_ERROR] {type(exc).__name__}: {exc}")
        logger.exception("detection_job_unhandled_error", job_id=job_str)


def execute_detection_job_background(
    job_id: uuid.UUID, session_factory: sessionmaker[Session], settings: Settings
) -> None:
    session = session_factory()
    try:
        execute_detection_job_in_session(job_id, session, settings)
    finally:
        session.close()


def _factory_for(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, expire_on_commit=False)


def dispatch_detection_job(*, job_id: uuid.UUID, db: Session, settings: Settings, run_async: bool = True) -> str:
    """Dispatch according to AI_WORKER_MODE. Returns the dispatch strategy used."""
    if settings.ai_worker_mode == "external":
        return "enqueued_external"
    factory = _factory_for(db)
    if run_async and settings.environment != "test":
        _worker_pool.submit(execute_detection_job_background, job_id, factory, settings)
        return "thread_pool"
    execute_detection_job_background(job_id, factory, settings)
    return "inline"


def run_pending_jobs_once(session_factory: sessionmaker[Session], settings: Settings, *, limit: int = 10) -> int:
    """Claim and execute up to `limit` queued jobs (oldest first). Returns number executed."""
    session = session_factory()
    try:
        ids = list(
            session.scalars(
                select(DetectionJob.id)
                .where(DetectionJob.status == "queued")
                .order_by(DetectionJob.created_at.asc())
                .limit(limit)
            ).all()
        )
    finally:
        session.close()

    executed = 0
    for job_id in ids:
        execute_detection_job_background(job_id, session_factory, settings)
        executed += 1
    return executed


def recover_interrupted_jobs(session_factory: sessionmaker[Session], settings: Settings) -> dict[str, int]:
    """Requeue jobs orphaned in 'processing' by a crash/restart, failing those over the attempt limit."""
    session = session_factory()
    requeued = failed = 0
    try:
        stuck = session.scalars(select(DetectionJob).where(DetectionJob.status == "processing")).all()
        for job in stuck:
            attempts = int((job.summary_json or {}).get("attempts", 0))
            if attempts >= settings.ai_max_job_attempts:
                job.status = "failed"
                job.error_message = f"[RECOVERY] Interrupted {attempts} times; attempt limit reached."
                job.completed_at = datetime.now(UTC)
                failed += 1
            else:
                session.execute(delete(DetectionItem).where(DetectionItem.job_id == job.id))
                job.status = "queued"
                job.progress_percent = 0
                job.error_message = None
                requeued += 1
        session.commit()
    finally:
        session.close()
    if requeued or failed:
        logger.warning("detection_jobs_recovered", requeued=requeued, failed=failed)
    return {"requeued": requeued, "failed": failed}


def resume_queued_jobs_in_thread_pool(session_factory: sessionmaker[Session], settings: Settings) -> int:
    session = session_factory()
    try:
        ids = list(session.scalars(select(DetectionJob.id).where(DetectionJob.status == "queued")).all())
    finally:
        session.close()
    for job_id in ids:
        _worker_pool.submit(execute_detection_job_background, job_id, session_factory, settings)
    return len(ids)


def warmup_available_models(settings: Settings) -> None:
    """Pre-load available YOLO weights into RAM in the background so the first inference is fast."""
    import os

    if not settings.ai_inference_enabled:
        return
    if os.environ.get("AI_WARMUP_ON_STARTUP", "true").lower() in ("0", "false", "no"):
        return

    def _preload() -> None:
        for entry in get_model_catalog():
            if entry.status != "available":
                continue
            try:
                model_runtime_cache.get_or_load(entry, requested_device=settings.ai_device)
                logger.info("ai_model_warmed_up", model_id=entry.model_id, device=settings.ai_device)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ai_model_warmup_failed", model_id=entry.model_id, error=str(exc))

    _worker_pool.submit(_preload)
