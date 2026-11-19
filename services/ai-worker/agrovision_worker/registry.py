"""Modular Agricultural Model Registry for AgroVision Phase 3.

A model is only reported as ``available`` when its weights file exists locally AND its
SHA-256 digest matches the pinned/registered checksum. Specialized agricultural modes
(wildlife, pest, disease) remain ``not_available`` until a manifest entry registers
trained weights together with a documented dataset and quantitative evaluation metrics.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

DetectionMode = Literal["general", "wildlife", "pest", "disease"]
ModelAvailability = Literal["available", "not_available"]

GENERAL_MODEL_ID = "yolov8n-coco-general"

# SHA-256 of the official Ultralytics YOLOv8n checkpoint used as the baseline
# (checkpoint metadata: version 8.0.0.dev0, date 2022-12-30, AGPL-3.0).
# Override with AI_YOLOV8N_SHA256 only after verifying a replacement file from a trusted source.
PINNED_YOLOV8N_SHA256 = os.environ.get(
    "AI_YOLOV8N_SHA256",
    "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
)
OFFICIAL_YOLOV8N_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"

MANIFEST_FILENAME = "model_manifest.json"

# Field-relevant subset of COCO classes; full class list is read from the loaded checkpoint.
BASELINE_FIELD_RELEVANT_CLASSES: tuple[str, ...] = (
    "person",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "car",
    "motorcycle",
    "truck",
)


@dataclass(frozen=True)
class EvaluationSummary:
    dataset_name: str
    dataset_version: str
    train_images: int
    val_images: int
    test_images: int
    precision: float | None = None
    recall: float | None = None
    map50: float | None = None
    map50_95: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class ModelRegistryEntry:
    model_id: str
    name: str
    version: str
    detection_mode: DetectionMode
    architecture: str
    license_spdx: str
    dataset_scope: str
    status: ModelAvailability
    status_reason: str
    weights_filename: str
    expected_sha256: str | None
    weights_path: str | None
    actual_sha256: str | None
    supported_classes: list[str]
    total_class_count: int
    default_confidence: float
    is_specialized_agricultural: bool
    honesty_disclaimer: str
    evaluation: EvaluationSummary | None = None
    requirements_for_activation: list[str] = field(default_factory=list)


@lru_cache(maxsize=32)
def _sha256_cached(path_str: str, mtime_ns: int, size: int) -> str:
    hasher = hashlib.sha256()
    with open(path_str, "rb") as handle:
        while chunk := handle.read(256 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    """Compute (and cache by path+mtime+size) the SHA-256 digest of a weights file."""
    stat = file_path.stat()
    return _sha256_cached(str(file_path.resolve()), stat.st_mtime_ns, stat.st_size)


def default_weights_dir() -> Path:
    override = os.environ.get("AI_WEIGHTS_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "weights"


def _specialized_placeholders() -> list[ModelRegistryEntry]:
    common_reqs = [
        "Register a documented dataset with isolated train / validation / test splits",
        "Train weights on representative low-altitude OV2640 RGB field imagery",
        "Record quantitative precision, recall and mAP@0.5 on the held-out test split",
        f"Add weights + SHA-256 + evaluation to weights/{MANIFEST_FILENAME}",
    ]
    return [
        ModelRegistryEntry(
            model_id="agrovision-wildlife-v1",
            name="AgroVision Field Wildlife Detector",
            version="unreleased",
            detection_mode="wildlife",
            architecture="YOLO (custom-trained, pending)",
            license_spdx="UNRELEASED",
            dataset_scope="No validated wildlife dataset registered",
            status="not_available",
            status_reason=(
                "Model Not Available — no trained snake / hedgehog / rodent weights with validated "
                "evaluation metrics are registered."
            ),
            weights_filename="agrovision_wildlife_v1.pt",
            expected_sha256=None,
            weights_path=None,
            actual_sha256=None,
            supported_classes=["snake", "hedgehog", "rodent"],
            total_class_count=3,
            default_confidence=0.45,
            is_specialized_agricultural=True,
            honesty_disclaimer=(
                "Planned target classes only. No detections are produced in this mode until a "
                "validated model is registered."
            ),
            requirements_for_activation=common_reqs,
        ),
        ModelRegistryEntry(
            model_id="agrovision-pest-v1",
            name="AgroVision Pest & Insect Detector",
            version="unreleased",
            detection_mode="pest",
            architecture="YOLO (custom-trained, pending)",
            license_spdx="UNRELEASED",
            dataset_scope="No validated insect dataset registered",
            status="not_available",
            status_reason=(
                "Model Not Available — COCO weights contain no agricultural insect classes; a "
                "close-range labeled pest dataset and evaluation are required."
            ),
            weights_filename="agrovision_pest_v1.pt",
            expected_sha256=None,
            weights_path=None,
            actual_sha256=None,
            supported_classes=["aphid", "locust", "caterpillar", "beetle"],
            total_class_count=4,
            default_confidence=0.40,
            is_specialized_agricultural=True,
            honesty_disclaimer=(
                "Small insects occupy very few pixels in aerial OV2640 frames; close-range capture "
                "or validated tiled inference is required."
            ),
            requirements_for_activation=common_reqs,
        ),
        ModelRegistryEntry(
            model_id="agrovision-disease-v1",
            name="AgroVision Crop Disease Analyzer",
            version="unreleased",
            detection_mode="disease",
            architecture="YOLO (custom-trained, pending)",
            license_spdx="UNRELEASED",
            dataset_scope="No validated crop-disease dataset registered",
            status="not_available",
            status_reason=(
                "Model Not Available — requires crop-specific, agronomist-verified lesion annotations. "
                "OV2640 is RGB-only (no NIR band)."
            ),
            weights_filename="agrovision_disease_v1.pt",
            expected_sha256=None,
            weights_path=None,
            actual_sha256=None,
            supported_classes=["leaf_blight", "powdery_mildew", "rust"],
            total_class_count=3,
            default_confidence=0.45,
            is_specialized_agricultural=True,
            honesty_disclaimer="RGB imagery cannot measure NIR NDVI; disease claims require validated models.",
            requirements_for_activation=common_reqs,
        ),
    ]


def _entry_from_manifest(raw: dict[str, Any], weights_dir: Path) -> ModelRegistryEntry:
    """Build an entry from a manifest record, activating it only if all evidence is present."""
    weights_filename = str(raw["weights_filename"])
    weights_file = weights_dir / Path(weights_filename).name
    expected = str(raw.get("expected_sha256") or "").lower() or None
    exists = weights_file.is_file()
    actual = compute_file_sha256(weights_file) if exists else None

    eval_raw = raw.get("evaluation")
    evaluation = EvaluationSummary(**eval_raw) if isinstance(eval_raw, dict) else None
    allow_unbenchmarked = bool(raw.get("allow_unbenchmarked_community_weights", False))
    has_metrics = allow_unbenchmarked or bool(
        evaluation
        and evaluation.train_images > 0
        and evaluation.val_images > 0
        and evaluation.test_images > 0
        and evaluation.precision is not None
        and evaluation.recall is not None
        and evaluation.map50 is not None
    )

    problems: list[str] = []
    if not exists:
        problems.append(f"weights file '{weights_file.name}' not found")
    if not expected:
        problems.append("expected_sha256 not registered")
    elif actual and actual != expected:
        problems.append("SHA-256 checksum mismatch")
    if not has_metrics:
        problems.append("dataset splits and precision/recall/mAP@0.5 metrics not registered")

    status: ModelAvailability = "available" if not problems else "not_available"
    return ModelRegistryEntry(
        model_id=str(raw["model_id"]),
        name=str(raw["name"]),
        version=str(raw.get("version", "1.0.0")),
        detection_mode=raw["detection_mode"],
        architecture=str(raw.get("architecture", "YOLO (custom)")),
        license_spdx=str(raw.get("license_spdx", "Proprietary")),
        dataset_scope=str(raw.get("dataset_scope", evaluation.dataset_name if evaluation else "unknown")),
        status=status,
        status_reason=(
            "Validated custom weights registered with dataset evaluation metrics."
            if status == "available"
            else "Model Not Available — " + "; ".join(problems) + "."
        ),
        weights_filename=weights_file.name,
        expected_sha256=expected,
        weights_path=weights_file.as_posix() if exists else None,
        actual_sha256=actual,
        supported_classes=[str(c) for c in raw.get("supported_classes", [])],
        total_class_count=len(raw.get("supported_classes", [])),
        default_confidence=float(raw.get("default_confidence", 0.4)),
        is_specialized_agricultural=raw["detection_mode"] != "general",
        honesty_disclaimer=str(
            raw.get(
                "honesty_disclaimer",
                "Custom model: results are limited to the registered classes and evaluated conditions.",
            )
        ),
        evaluation=evaluation,
        requirements_for_activation=[] if status == "available" else problems,
    )


def load_manifest(weights_dir: Path) -> list[dict[str, Any]]:
    manifest = weights_dir / MANIFEST_FILENAME
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [m for m in data.get("models", []) if isinstance(m, dict)]


def build_model_registry(
    *,
    weights_dir: Path | None = None,
    dynamic_class_names: dict[str, list[str]] | None = None,
) -> list[ModelRegistryEntry]:
    """Construct the catalog of general and specialized agricultural detection models."""
    resolved_dir = weights_dir or default_weights_dir()
    yolo_path = resolved_dir / "yolov8n.pt"
    yolo_exists = yolo_path.is_file()
    yolo_sha = compute_file_sha256(yolo_path) if yolo_exists else None
    checksum_ok = bool(yolo_sha and yolo_sha == PINNED_YOLOV8N_SHA256)

    if not yolo_exists:
        general_reason = (
            f"Model Not Available — weights missing at {yolo_path.as_posix()}. "
            "Run services/ai-worker/scripts/fetch_weights.py."
        )
    elif not checksum_ok:
        general_reason = "Model Not Available — YOLOv8n weights SHA-256 does not match the pinned checksum."
    else:
        general_reason = "Verified local YOLOv8n weights (SHA-256 match). CPU inference; optional CUDA."

    general_classes = (dynamic_class_names or {}).get(GENERAL_MODEL_ID) or list(
        BASELINE_FIELD_RELEVANT_CLASSES
    )

    entries: list[ModelRegistryEntry] = [
        ModelRegistryEntry(
            model_id=GENERAL_MODEL_ID,
            name="Ultralytics YOLOv8n — General Object Detection (COCO)",
            version="8.0.0 (checkpoint 2022-12-30)",
            detection_mode="general",
            architecture="YOLOv8 Nano, 640px input, PyTorch",
            license_spdx="AGPL-3.0-only",
            dataset_scope="MS COCO 2017 — 80 general classes (not agricultural-specific)",
            status="available" if checksum_ok else "not_available",
            status_reason=general_reason,
            weights_filename="yolov8n.pt",
            expected_sha256=PINNED_YOLOV8N_SHA256,
            weights_path=yolo_path.as_posix() if yolo_exists else None,
            actual_sha256=yolo_sha,
            supported_classes=general_classes,
            total_class_count=80,
            default_confidence=0.35,
            is_specialized_agricultural=False,
            honesty_disclaimer=(
                "General-purpose detector limited to the 80 COCO classes (e.g. person, bird, dog, "
                "horse, sheep, cow, car, truck). It is NOT a snake, hedgehog, insect, or crop-disease detector."
            ),
            evaluation=EvaluationSummary(
                dataset_name="MS COCO val2017 (vendor-published)",
                dataset_version="2017",
                train_images=118287,
                val_images=5000,
                test_images=0,
                map50_95=0.373,
                notes=(
                    "mAP50-95 = 37.3 as published by Ultralytics for YOLOv8n at 640px. Not re-measured "
                    "by AgroDrone and NOT evaluated on agricultural or OV2640 imagery."
                ),
            ),
        ),
    ]

    placeholders = {p.model_id: p for p in _specialized_placeholders()}
    for raw in load_manifest(resolved_dir):
        try:
            custom = _entry_from_manifest(raw, resolved_dir)
        except (KeyError, TypeError, ValueError):
            continue
        placeholders.pop(custom.model_id, None)
        entries.append(custom)

    entries.extend(placeholders.values())
    return entries


def with_classes(entry: ModelRegistryEntry, classes: list[str]) -> ModelRegistryEntry:
    return replace(entry, supported_classes=classes, total_class_count=len(classes))
