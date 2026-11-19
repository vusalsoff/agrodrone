"""Real-model smoke tests: the actual pinned YOLOv8n checkpoint on a real photograph.

Uses the Ultralytics-bundled `bus.jpg` sample (street scene with a bus and pedestrians).
Skipped automatically when the weights or the inference runtime are unavailable.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from agrovision_worker.registry import GENERAL_MODEL_ID, build_model_registry
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services import vision
from tests.media_fixtures import make_mp4

pytestmark = pytest.mark.real_model

try:
    from ultralytics.utils import ASSETS

    BUS_JPG = Path(ASSETS) / "bus.jpg"
except Exception:  # noqa: BLE001
    BUS_JPG = Path("missing")

_general = next(e for e in build_model_registry() if e.model_id == GENERAL_MODEL_ID)
_skip = pytest.mark.skipif(
    _general.status != "available" or not BUS_JPG.exists(),
    reason="YOLOv8n weights or Ultralytics runtime not available",
)


@_skip
def test_real_yolov8n_inference_on_photograph() -> None:
    from agrovision_worker.engine import analyze_image_bytes

    result = analyze_image_bytes(BUS_JPG.read_bytes(), model_entry=_general, confidence_threshold=0.4)
    labels = {d.label for d in result.detections}
    assert "person" in labels
    assert "bus" in labels
    assert result.model_checksum == _general.expected_sha256
    assert result.device_used in {"cpu", "cuda", "cuda:0"}
    assert result.inference_ms > 0
    for d in result.detections:
        assert 0.4 <= d.confidence <= 1.0
        assert 0 <= d.bbox_x1 < d.bbox_x2 <= result.width_px
        assert 0 <= d.bbox_y1 < d.bbox_y2 <= result.height_px


@_skip
def test_real_model_end_to_end_api_flow(
    client: TestClient, test_settings: Settings, register_user: Callable[..., dict[str, Any]]
) -> None:
    test_settings.ai_inference_enabled = True
    test_settings.max_image_upload_bytes = 5 * 1024 * 1024
    vision.set_test_predictors(None, None)

    user = register_user("real@agrodrone.dev", role="agronomist")
    up = client.post(
        "/api/v1/media/upload",
        headers=user["headers"],
        files={"file": ("bus.jpg", BUS_JPG.read_bytes(), "image/jpeg")},
    )
    assert up.status_code == 201, up.text

    job = client.post(
        "/api/v1/detections/jobs",
        headers=user["headers"],
        json={"media_asset_id": up.json()["id"], "model_id": GENERAL_MODEL_ID, "confidence_threshold": 0.4},
    ).json()
    assert job["status"] == "completed", job.get("error_message")
    assert job["summary_json"]["class_counts"].get("person", 0) >= 1
    assert job["model_checksum"] == _general.expected_sha256

    annotated = client.get(f"/api/v1/detections/jobs/{job['id']}/annotated", headers=user["headers"])
    assert annotated.status_code == 200 and annotated.content.startswith(b"\xff\xd8\xff")


@_skip
def test_real_model_video_sampling_runs(
    client: TestClient, test_settings: Settings, register_user: Callable[..., dict[str, Any]]
) -> None:
    """Synthetic clip contains no COCO objects: real model must return zero (not invented) detections."""
    test_settings.ai_inference_enabled = True
    vision.set_test_predictors(None, None)
    user = register_user("realvid@agrodrone.dev")
    up = client.post(
        "/api/v1/media/upload",
        headers=user["headers"],
        files={"file": ("synthetic.mp4", make_mp4(seconds=2.0, fps=10), "video/mp4")},
    )
    job = client.post(
        "/api/v1/detections/jobs",
        headers=user["headers"],
        json={"media_asset_id": up.json()["id"], "model_id": GENERAL_MODEL_ID, "frame_sample_interval_ms": 1000},
    ).json()
    assert job["status"] == "completed", job.get("error_message")
    assert job["total_frames_sampled"] == 2
    assert job["summary_json"]["sampling_mode"] == "sampled_frames_only"
