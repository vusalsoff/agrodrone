"""Unit tests for the AgroVision engine: registry, bbox serialization/validation, decoding, video sampling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from agrovision_worker.engine import (
    InferenceEngineError,
    RawDetectionBox,
    _LoadedModelHandle,
    _predict_on_rgb_array,
    analyze_image_bytes,
    analyze_video_bytes,
    decode_image_safely,
    render_annotated_jpeg,
)
from agrovision_worker.registry import (
    GENERAL_MODEL_ID,
    PINNED_YOLOV8N_SHA256,
    build_model_registry,
)

from tests.media_fixtures import make_corrupt_png, make_mp4, make_png


def _general_entry() -> Any:
    return next(e for e in build_model_registry() if e.model_id == GENERAL_MODEL_ID)


def test_registry_general_available_and_specialized_not_available() -> None:
    entries = {e.model_id: e for e in build_model_registry()}
    general = entries[GENERAL_MODEL_ID]
    assert general.status == "available"
    assert general.actual_sha256 == PINNED_YOLOV8N_SHA256
    assert general.is_specialized_agricultural is False
    assert "NOT a snake" in general.honesty_disclaimer

    for mid in ("agrovision-wildlife-v1", "agrovision-pest-v1", "agrovision-disease-v1"):
        assert entries[mid].status == "not_available"
        assert entries[mid].status_reason.startswith("Model Not Available")
        assert entries[mid].weights_path is None
        assert entries[mid].evaluation is None


def test_registry_missing_weights_marks_general_unavailable(tmp_path: Path) -> None:
    entries = {e.model_id: e for e in build_model_registry(weights_dir=tmp_path)}
    assert entries[GENERAL_MODEL_ID].status == "not_available"
    assert "weights missing" in entries[GENERAL_MODEL_ID].status_reason


def test_manifest_custom_model_requires_checksum_and_metrics(tmp_path: Path) -> None:
    import hashlib
    import json

    weights = tmp_path / "custom_pest.pt"
    weights.write_bytes(b"fake-weights-for-registry-test")
    sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    base = {
        "model_id": "agrovision-pest-v1",
        "name": "Custom Pest",
        "detection_mode": "pest",
        "weights_filename": "custom_pest.pt",
        "expected_sha256": sha,
        "supported_classes": ["aphid"],
    }
    (tmp_path / "model_manifest.json").write_text(json.dumps({"models": [base]}), encoding="utf-8")
    entry = {e.model_id: e for e in build_model_registry(weights_dir=tmp_path)}["agrovision-pest-v1"]
    assert entry.status == "not_available"
    assert "metrics not registered" in entry.status_reason

    base["evaluation"] = {
        "dataset_name": "pest-ds",
        "dataset_version": "1",
        "train_images": 800,
        "val_images": 100,
        "test_images": 100,
        "precision": 0.81,
        "recall": 0.74,
        "map50": 0.78,
    }
    (tmp_path / "model_manifest.json").write_text(json.dumps({"models": [base]}), encoding="utf-8")
    entry = {e.model_id: e for e in build_model_registry(weights_dir=tmp_path)}["agrovision-pest-v1"]
    assert entry.status == "available"


# --- bbox serialization & validation via a fake Ultralytics result -------------------------


class _Arr:
    def __init__(self, data: list[Any]) -> None:
        self._d = np.asarray(data, dtype=np.float32)

    def cpu(self) -> _Arr:
        return self

    def numpy(self) -> np.ndarray:
        return self._d


@dataclass
class _Boxes:
    xyxy: _Arr
    conf: _Arr
    cls: _Arr

    def __len__(self) -> int:
        return len(self.conf.numpy())


class _FakeModel:
    def __init__(self, rows: list[tuple[list[float], float, int]]) -> None:
        self.rows = rows

    def predict(self, **_: Any) -> list[Any]:
        if not self.rows:
            return [type("R", (), {"boxes": None})()]
        boxes = _Boxes(
            xyxy=_Arr([r[0] for r in self.rows]),
            conf=_Arr([r[1] for r in self.rows]),
            cls=_Arr([r[2] for r in self.rows]),
        )
        return [type("R", (), {"boxes": boxes})()]


def test_bbox_serialization_clipping_and_filtering() -> None:
    rgb = np.zeros((100, 200, 3), dtype=np.uint8)
    handle = _LoadedModelHandle(
        model=_FakeModel(
            [
                ([10.4, 20.6, 50.2, 80.9], 0.91234, 0),  # valid
                ([-15.0, -5.0, 250.0, 130.0], 0.77, 16),  # out of bounds -> clipped
                ([30.0, 30.0, 30.0, 60.0], 0.88, 2),  # zero width -> dropped
                ([5.0, 5.0, 40.0, 40.0], 0.10, 2),  # below threshold -> dropped
            ]
        ),
        checksum="abc",
        device="cpu",
        class_names={0: "person", 2: "car", 16: "dog"},
    )
    boxes = _predict_on_rgb_array(rgb, handle=handle, confidence_threshold=0.35)
    assert [b.label for b in boxes] == ["person", "dog"]
    assert boxes[0].confidence == 0.9123
    assert (boxes[0].bbox_x1, boxes[0].bbox_y1, boxes[0].bbox_x2, boxes[0].bbox_y2) == (10.4, 20.6, 50.2, 80.9)
    dog = boxes[1]
    assert (dog.bbox_x1, dog.bbox_y1, dog.bbox_x2, dog.bbox_y2) == (0.0, 0.0, 200.0, 100.0)
    for b in boxes:
        assert 0 <= b.bbox_x1 < b.bbox_x2 <= 200 and 0 <= b.bbox_y1 < b.bbox_y2 <= 100


def test_empty_detections_produce_valid_result() -> None:
    entry = _general_entry()
    result = analyze_image_bytes(make_png(80, 60), model_entry=entry, custom_predictor=lambda _rgb, _c: [])
    assert result.detections == []
    assert result.class_counts == {}
    assert (result.width_px, result.height_px) == (80, 60)
    assert result.annotated_jpeg_bytes.startswith(b"\xff\xd8\xff")


def test_invalid_media_and_limits_raise_structured_errors() -> None:
    with pytest.raises(InferenceEngineError) as exc:
        decode_image_safely(make_corrupt_png())
    assert exc.value.code == "IMAGE_DECODE_FAILED"

    with pytest.raises(InferenceEngineError) as exc:
        decode_image_safely(b"")
    assert exc.value.code == "EMPTY_IMAGE"

    with pytest.raises(InferenceEngineError) as exc:
        decode_image_safely(make_png(300, 20), max_dimension_px=256)
    assert exc.value.code == "IMAGE_RESOLUTION_EXCEEDED"

    with pytest.raises(InferenceEngineError) as exc:
        analyze_image_bytes(make_png(), model_entry=_general_entry(), confidence_threshold=0.01)
    assert exc.value.code == "INVALID_CONFIDENCE_THRESHOLD"


def test_model_not_available_is_rejected() -> None:
    pest = next(e for e in build_model_registry() if e.model_id == "agrovision-pest-v1")
    with pytest.raises(InferenceEngineError) as exc:
        analyze_image_bytes(make_png(), model_entry=pest)
    assert exc.value.code == "MODEL_NOT_AVAILABLE"


def test_annotated_render_is_jpeg() -> None:
    rgb = np.zeros((60, 80, 3), dtype=np.uint8)
    jpeg = render_annotated_jpeg(rgb, [RawDetectionBox(0, "person", 0.9, 5, 5, 40, 50)])
    assert jpeg.startswith(b"\xff\xd8\xff") and len(jpeg) > 200


def test_video_frame_sampling_timestamps_and_limits() -> None:
    entry = _general_entry()
    video = make_mp4(seconds=3.0, fps=10)
    calls: list[tuple[int, int]] = []

    def predictor(rgb: np.ndarray, conf: float, idx: int, ts: int) -> list[RawDetectionBox]:
        calls.append((idx, ts))
        return [RawDetectionBox(0, "person", 0.8, 10, 10, 50, 50, frame_index=idx, timestamp_ms=ts)]

    progress: list[int] = []
    result = analyze_video_bytes(
        video,
        model_entry=entry,
        frame_sample_interval_ms=500,
        max_frames=20,
        progress_callback=progress.append,
        custom_predictor=predictor,
    )
    # 30 frames @10fps, every 5th frame -> 6 sampled frames at 0,500,...,2500 ms
    assert result.total_frames_sampled == 6
    assert [ts for _, ts in calls] == [0, 500, 1000, 1500, 2000, 2500]
    assert result.total_video_frames == 30
    assert result.frame_sample_interval_ms == 500
    assert len(result.detections) == 6
    assert progress and max(progress) <= 95

    capped = analyze_video_bytes(video, model_entry=entry, frame_sample_interval_ms=200, max_frames=3, custom_predictor=predictor)
    assert capped.total_frames_sampled == 3

    with pytest.raises(InferenceEngineError) as exc:
        analyze_video_bytes(video, model_entry=entry, max_duration_seconds=1, custom_predictor=predictor)
    assert exc.value.code == "VIDEO_DURATION_EXCEEDED"

    with pytest.raises(InferenceEngineError) as exc:
        analyze_video_bytes(video, model_entry=entry, cancel_check=lambda: True, custom_predictor=predictor)
    assert exc.value.code == "JOB_CANCELLED"

    with pytest.raises(InferenceEngineError) as exc:
        analyze_video_bytes(b"not a real video container", model_entry=entry, custom_predictor=predictor)
    assert exc.value.code in {"VIDEO_DECODE_FAILED", "VIDEO_NO_READABLE_FRAMES"}
