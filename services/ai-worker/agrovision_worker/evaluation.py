"""Evaluation hooks for registering custom agricultural models.

Runs Ultralytics validation on a documented dataset YAML (train/val/test splits) and
returns metrics in the exact shape accepted by POST /api/v1/detections/datasets and the
weights/model_manifest.json ``evaluation`` block. Nothing is estimated: if validation
cannot run, an exception is raised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def count_split_images(data_yaml: Path) -> dict[str, int]:
    """Count image files referenced by each split of a YOLO dataset YAML."""
    spec = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    root = Path(spec.get("path") or data_yaml.parent)
    if not root.is_absolute():
        root = (data_yaml.parent / root).resolve()
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    counts: dict[str, int] = {}
    for split in ("train", "val", "test"):
        rel = spec.get(split)
        if not rel:
            counts[split] = 0
            continue
        split_dir = root / rel
        counts[split] = sum(1 for p in split_dir.rglob("*") if p.suffix.lower() in exts) if split_dir.exists() else 0
    return counts


def evaluate_model(weights: Path, data_yaml: Path, *, split: str = "test", imgsz: int = 640) -> dict[str, Any]:
    """Run real Ultralytics validation and return precision / recall / mAP metrics."""
    from ultralytics import YOLO  # type: ignore[import-not-found]

    counts = count_split_images(data_yaml)
    if min(counts.values()) <= 0:
        raise ValueError(f"Dataset must define non-empty train/val/test splits, got {counts}.")

    model = YOLO(str(weights))
    metrics = model.val(data=str(data_yaml), split=split, imgsz=imgsz, verbose=False)
    box = metrics.box
    return {
        "train_images": counts["train"],
        "val_images": counts["val"],
        "test_images": counts["test"],
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "map50": round(float(box.map50), 4),
        "map50_95": round(float(box.map), 4),
        "evaluated_split": split,
    }
