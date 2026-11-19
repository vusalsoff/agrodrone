"""API integration tests for AgroVision detection jobs, review, export, isolation, and worker durability."""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from typing import Any

import numpy as np
import pytest
from agrovision_worker.engine import RawDetectionBox
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.services import vision
from tests.media_fixtures import make_corrupt_png, make_mp4, make_png

GENERAL = "yolov8n-coco-general"


def _fixed_image_predictor(rgb: np.ndarray, conf: float) -> list[RawDetectionBox]:
    h, w = rgb.shape[:2]
    return [
        RawDetectionBox(19, "cow", 0.88, 2.0, 3.0, w * 0.5, h * 0.6),
        RawDetectionBox(0, "person", 0.61, w * 0.55, 1.0, w - 1.0, h - 2.0),
    ]


def _fixed_video_predictor(rgb: np.ndarray, conf: float, idx: int, ts: int) -> list[RawDetectionBox]:
    return [RawDetectionBox(18, "sheep", 0.7, 5, 5, 40, 40, frame_index=idx, timestamp_ms=ts)]


@pytest.fixture(autouse=True)
def _ai_enabled(test_settings: Settings) -> Generator[None, None, None]:
    test_settings.ai_inference_enabled = True
    vision.set_test_predictors(_fixed_image_predictor, _fixed_video_predictor)
    yield
    vision.set_test_predictors(None, None)


def _upload(client: TestClient, headers: dict[str, str], name: str, data: bytes, mime: str) -> dict[str, Any]:
    res = client.post("/api/v1/media/upload", headers=headers, files={"file": (name, data, mime)})
    assert res.status_code == 201, res.text
    return res.json()


def _create_job(client: TestClient, headers: dict[str, str], media_id: str, **extra: Any) -> Any:
    return client.post(
        "/api/v1/detections/jobs",
        headers=headers,
        json={"media_asset_id": media_id, "model_id": GENERAL, "confidence_threshold": 0.3, **extra},
    )


def test_model_registry_endpoint_reports_honest_availability(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    user = register_user("models@agrodrone.dev")
    res = client.get("/api/v1/detections/models", headers=user["headers"])
    assert res.status_code == 200
    models = {m["model_id"]: m for m in res.json()}
    assert models[GENERAL]["status"] == "available"
    assert models[GENERAL]["total_class_count"] == 80
    assert "cow" in models[GENERAL]["supported_classes"]
    assert models[GENERAL]["is_specialized_agricultural"] is False
    for mid in ("agrovision-wildlife-v1", "agrovision-pest-v1", "agrovision-disease-v1"):
        assert models[mid]["status"] == "not_available"
        assert models[mid]["requirements_for_activation"]


def test_image_job_lifecycle_persists_results_and_annotated_image(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("owner@agrodrone.dev", role="agronomist")
    asset = _upload(client, owner["headers"], "plot.png", make_png(120, 80), "image/png")

    res = _create_job(client, owner["headers"], asset["id"])
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] == "completed"
    assert job["progress_percent"] == 100
    assert job["model_checksum"] and len(job["model_checksum"]) == 64
    assert job["dataset_scope"].startswith("MS COCO")
    assert job["summary_json"]["total_detections"] == 2
    assert job["summary_json"]["class_counts"] == {"cow": 1, "person": 1}
    assert job["summary_json"]["width_px"] == 120
    assert job["inference_ms"] >= 1
    assert job["started_at"] and job["completed_at"]

    items = job["items"]
    assert [i["label"] for i in items] == ["cow", "person"]
    for item in items:
        assert item["original_label"] == item["label"]
        assert item["original_confidence"] == item["confidence"]
        assert item["review_status"] == "unreviewed"
        assert 0 <= item["bbox_x1"] < item["bbox_x2"] <= 120

    annotated = client.get(f"/api/v1/detections/jobs/{job['id']}/annotated", headers=owner["headers"])
    assert annotated.status_code == 200
    assert annotated.content.startswith(b"\xff\xd8\xff")
    assert annotated.headers["X-Content-Type-Options"] == "nosniff"

    dl = client.get(f"/api/v1/detections/jobs/{job['id']}/annotated?download=true", headers=owner["headers"])
    assert dl.headers["Content-Disposition"].startswith("attachment;")


def test_empty_detection_result(client: TestClient, register_user: Callable[..., dict[str, Any]]) -> None:
    vision.set_test_predictors(lambda _rgb, _c: [], _fixed_video_predictor)
    owner = register_user("empty@agrodrone.dev")
    asset = _upload(client, owner["headers"], "bare.png", make_png(), "image/png")
    job = _create_job(client, owner["headers"], asset["id"]).json()
    assert job["status"] == "completed"
    assert job["items"] == []
    assert job["summary_json"]["total_detections"] == 0
    assert job["summary_json"]["average_confidence"] is None


def test_specialized_and_unknown_models_are_rejected(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("spec@agrodrone.dev")
    asset = _upload(client, owner["headers"], "a.png", make_png(), "image/png")
    for model_id in ("agrovision-wildlife-v1", "agrovision-pest-v1", "agrovision-disease-v1"):
        res = client.post(
            "/api/v1/detections/jobs",
            headers=owner["headers"],
            json={"media_asset_id": asset["id"], "model_id": model_id},
        )
        assert res.status_code == 422
        assert "Model Not Available" in res.json()["error"]["message"]
        assert res.json()["error"]["details"]["status"] == "not_available"

    unknown = client.post(
        "/api/v1/detections/jobs",
        headers=owner["headers"],
        json={"media_asset_id": asset["id"], "model_id": "made-up-model"},
    )
    assert unknown.status_code == 422


def test_inference_disabled_returns_501(
    client: TestClient, test_settings: Settings, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("disabled@agrodrone.dev")
    asset = _upload(client, owner["headers"], "a.png", make_png(), "image/png")
    test_settings.ai_inference_enabled = False
    res = _create_job(client, owner["headers"], asset["id"])
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_invalid_media_fails_job_and_worker_error_recovers_on_retry(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("fail@agrodrone.dev")
    corrupt = _upload(client, owner["headers"], "broken.png", make_corrupt_png(), "image/png")
    failed = _create_job(client, owner["headers"], corrupt["id"]).json()
    assert failed["status"] == "failed"
    assert failed["error_message"].startswith("[IMAGE_DECODE_FAILED]")
    assert failed["items"] == []
    assert failed["annotated_storage_key"] is None

    good = _upload(client, owner["headers"], "ok.png", make_png(), "image/png")

    def _boom(_rgb: np.ndarray, _c: float) -> list[RawDetectionBox]:
        raise RuntimeError("simulated GPU/driver crash")

    vision.set_test_predictors(_boom, _fixed_video_predictor)
    crashed = _create_job(client, owner["headers"], good["id"]).json()
    assert crashed["status"] == "failed"
    assert "[WORKER_ERROR] RuntimeError" in crashed["error_message"]

    # Retrying a completed job is not allowed; retrying a failed job is safe and idempotent.
    vision.set_test_predictors(_fixed_image_predictor, _fixed_video_predictor)
    retried = client.post(
        f"/api/v1/detections/jobs/{crashed['id']}/retry?run_async=false", headers=owner["headers"]
    ).json()
    assert retried["status"] == "completed"
    assert len(retried["items"]) == 2
    assert retried["summary_json"]["retry_count"] == 1
    again = client.post(f"/api/v1/detections/jobs/{crashed['id']}/retry", headers=owner["headers"])
    assert again.status_code == 409


def test_external_worker_mode_cancel_retry_and_durable_claim(
    client: TestClient,
    test_settings: Settings,
    db_session: Session,
    register_user: Callable[..., dict[str, Any]],
) -> None:
    owner = register_user("queue@agrodrone.dev")
    asset = _upload(client, owner["headers"], "q.png", make_png(), "image/png")
    test_settings.ai_worker_mode = "external"

    queued = _create_job(client, owner["headers"], asset["id"]).json()
    assert queued["status"] == "queued"

    cancelled = client.post(f"/api/v1/detections/jobs/{queued['id']}/cancel", headers=owner["headers"])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/detections/jobs/{queued['id']}/cancel", headers=owner["headers"]).status_code == 409

    requeued = client.post(f"/api/v1/detections/jobs/{queued['id']}/retry", headers=owner["headers"]).json()
    assert requeued["status"] == "queued"

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert vision.run_pending_jobs_once(factory, test_settings) == 1
    # A second drain finds nothing: the CAS claim prevents double execution.
    assert vision.run_pending_jobs_once(factory, test_settings) == 0
    assert vision.claim_job(factory(), __import__("uuid").UUID(queued["id"])) is False

    done = client.get(f"/api/v1/detections/jobs/{queued['id']}", headers=owner["headers"]).json()
    assert done["status"] == "completed"
    assert done["summary_json"]["attempts"] == 1


def test_crash_recovery_requeues_orphaned_processing_jobs(
    client: TestClient,
    test_settings: Settings,
    db_session: Session,
    register_user: Callable[..., dict[str, Any]],
) -> None:
    from app.models.detection import DetectionJob

    owner = register_user("recover@agrodrone.dev")
    asset = _upload(client, owner["headers"], "r.png", make_png(), "image/png")
    test_settings.ai_worker_mode = "external"
    job_id = _create_job(client, owner["headers"], asset["id"]).json()["id"]

    job = db_session.get(DetectionJob, __import__("uuid").UUID(job_id))
    job.status = "processing"
    job.summary_json = {"attempts": 1}
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert vision.recover_interrupted_jobs(factory, test_settings) == {"requeued": 1, "failed": 0}
    assert vision.run_pending_jobs_once(factory, test_settings) == 1

    db_session.expire_all()
    job = db_session.get(DetectionJob, __import__("uuid").UUID(job_id))
    job.status = "processing"
    job.summary_json = {"attempts": test_settings.ai_max_job_attempts}
    db_session.commit()
    assert vision.recover_interrupted_jobs(factory, test_settings) == {"requeued": 0, "failed": 1}


def test_video_job_sampled_frames_metadata_and_frame_previews(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("video@agrodrone.dev", role="agronomist")
    asset = _upload(client, owner["headers"], "pass.mp4", make_mp4(seconds=2.0, fps=10), "video/mp4")
    assert asset["media_type"] == "video"

    job = _create_job(
        client, owner["headers"], asset["id"], frame_sample_interval_ms=500, max_frames=10
    ).json()
    assert job["status"] == "completed", job.get("error_message")
    assert job["media_type"] == "video"
    assert job["total_frames_sampled"] == 4
    summary = job["summary_json"]
    assert summary["sampling_mode"] == "sampled_frames_only"
    assert "NOT full-frame analysis" in summary["sampling_notice"]
    assert [f["timestamp_ms"] for f in summary["sampled_frames"]] == [0, 500, 1000, 1500]
    assert {i["frame_index"] for i in job["items"]} == {0, 1, 2, 3}
    assert all(i["timestamp_ms"] is not None for i in job["items"])

    frame = client.get(f"/api/v1/detections/jobs/{job['id']}/frames/2/annotated", headers=owner["headers"])
    assert frame.status_code == 200 and frame.content.startswith(b"\xff\xd8\xff")
    missing = client.get(f"/api/v1/detections/jobs/{job['id']}/frames/9/annotated", headers=owner["headers"])
    assert missing.status_code == 404


def test_human_review_preserves_machine_output_and_export(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    owner = register_user("review@agrodrone.dev", full_name="Field Reviewer", role="agronomist")
    asset = _upload(client, owner["headers"], "rev.png", make_png(), "image/png")
    job = _create_job(client, owner["headers"], asset["id"]).json()
    cow, person = job["items"]

    confirmed = client.patch(
        f"/api/v1/detections/items/{cow['id']}/review",
        headers=owner["headers"],
        json={"review_status": "confirmed", "reviewer_notes": "Holstein near water trough"},
    ).json()
    assert confirmed["review_status"] == "confirmed"
    assert confirmed["reviewer_id"] == owner["user"]["id"]
    assert confirmed["reviewed_at"] is not None

    corrected = client.patch(
        f"/api/v1/detections/items/{person['id']}/review",
        headers=owner["headers"],
        json={"review_status": "uncertain", "corrected_label": "scarecrow"},
    ).json()
    assert corrected["label"] == "scarecrow"
    assert corrected["original_label"] == "person"
    assert corrected["original_confidence"] == person["confidence"]

    rejected = client.patch(
        f"/api/v1/detections/items/{person['id']}/review",
        headers=owner["headers"],
        json={"review_status": "rejected"},
    )
    assert rejected.status_code == 200
    bad = client.patch(
        f"/api/v1/detections/items/{person['id']}/review",
        headers=owner["headers"],
        json={"review_status": "approved"},
    )
    assert bad.status_code == 422

    detail = client.get(f"/api/v1/detections/jobs/{job['id']}", headers=owner["headers"]).json()
    assert detail["summary_json"]["review_counts"] == {
        "unreviewed": 0,
        "confirmed": 1,
        "rejected": 1,
        "uncertain": 0,
    }

    export = client.get(f"/api/v1/detections/jobs/{job['id']}/export", headers=owner["headers"])
    assert export.status_code == 200
    assert export.headers["Content-Disposition"].startswith("attachment;")
    report = json.loads(export.content)
    assert report["schema_version"] == "agrodrone.agrovision.v3"
    assert report["model_provenance"]["model_checksum_sha256"] == job["model_checksum"]
    person_row = next(d for d in report["detections"] if d["id"] == person["id"])
    assert person_row["machine_prediction"]["label"] == "person"
    assert person_row["human_review"]["verified_label"] == "scarecrow"
    assert person_row["human_review"]["review_status"] == "rejected"


def test_history_filters_sorting_and_cross_user_isolation(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    admin = register_user("root@agrodrone.dev")
    owner = register_user("alice@agrodrone.dev", role="agronomist")
    other = register_user("bob@agrodrone.dev", role="operator")
    viewer = register_user("vera@agrodrone.dev", role="viewer")

    img = _upload(client, owner["headers"], "north_block.png", make_png(), "image/png")
    vid = _upload(client, owner["headers"], "sweep.mp4", make_mp4(seconds=1.0), "video/mp4")
    j1 = _create_job(client, owner["headers"], img["id"]).json()
    j2 = _create_job(client, owner["headers"], vid["id"], frame_sample_interval_ms=500).json()

    def _list(user: dict[str, Any], query: str = "") -> dict[str, Any]:
        r = client.get(f"/api/v1/detections/jobs{query}", headers=user["headers"])
        assert r.status_code == 200, r.text
        return r.json()

    assert _list(owner)["total"] == 2
    assert _list(owner, "?media_type=video")["items"][0]["id"] == j2["id"]
    assert _list(owner, "?q=north_block")["items"][0]["id"] == j1["id"]
    assert _list(owner, f"?model_id={GENERAL}&status=completed")["total"] == 2
    assert _list(owner, "?review_status=confirmed")["total"] == 0
    assert _list(owner, "?sort_by=oldest")["items"][0]["id"] == j1["id"]
    assert _list(owner, "?date_from=2099-01-01T00:00:00Z")["total"] == 0
    assert _list(admin)["total"] == 2
    assert _list(other)["total"] == 0

    # Cross-user isolation on every job-scoped endpoint.
    item_id = j1["items"][0]["id"]
    for path in (
        f"/api/v1/detections/jobs/{j1['id']}",
        f"/api/v1/detections/jobs/{j1['id']}/annotated",
        f"/api/v1/detections/jobs/{j1['id']}/export",
        f"/api/v1/detections/jobs/{j2['id']}/frames/0/annotated",
    ):
        assert client.get(path, headers=other["headers"]).status_code == 403
    assert client.post(f"/api/v1/detections/jobs/{j1['id']}/cancel", headers=other["headers"]).status_code == 403
    assert client.delete(f"/api/v1/detections/jobs/{j1['id']}", headers=other["headers"]).status_code == 403
    assert (
        client.patch(
            f"/api/v1/detections/items/{item_id}/review",
            headers=other["headers"],
            json={"review_status": "confirmed"},
        ).status_code
        == 403
    )
    # Other users cannot analyze someone else's media.
    assert _create_job(client, other["headers"], img["id"]).status_code == 403
    # Viewers cannot start analysis or review.
    assert _create_job(client, viewer["headers"], img["id"]).status_code == 403
    # Unauthenticated access is rejected.
    client.cookies.clear()
    assert client.get(f"/api/v1/detections/jobs/{j1['id']}/annotated").status_code == 401

    # Owner deletes job; annotated artifact disappears.
    assert client.delete(f"/api/v1/detections/jobs/{j1['id']}", headers=owner["headers"]).status_code == 204
    assert client.get(f"/api/v1/detections/jobs/{j1['id']}", headers=owner["headers"]).status_code == 404


def test_dataset_registration_requires_splits_and_metrics(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    _admin = register_user("ds-admin@agrodrone.dev")
    agro = register_user("ds-agro@agrodrone.dev", role="agronomist")
    viewer = register_user("ds-view@agrodrone.dev", role="viewer")

    payload = {
        "name": "OV2640 Wheat Rust v1",
        "version": "1.0",
        "detection_mode": "disease",
        "classes": ["rust"],
        "train_count": 700,
        "val_count": 150,
        "test_count": 150,
        "metrics": {"precision": 0.71, "recall": 0.64, "map50": 0.66},
    }
    assert client.post("/api/v1/detections/datasets", headers=viewer["headers"], json=payload).status_code == 403
    missing_metrics = {k: v for k, v in payload.items() if k != "metrics"}
    assert client.post("/api/v1/detections/datasets", headers=agro["headers"], json=missing_metrics).status_code == 422
    zero_test = {**payload, "test_count": 0}
    assert client.post("/api/v1/detections/datasets", headers=agro["headers"], json=zero_test).status_code == 422

    created = client.post("/api/v1/detections/datasets", headers=agro["headers"], json=payload)
    assert created.status_code == 201
    assert created.json()["metrics_json"]["map50"] == 0.66
    assert client.post("/api/v1/detections/datasets", headers=agro["headers"], json=payload).status_code == 409

    listed = client.get("/api/v1/detections/datasets?detection_mode=disease", headers=agro["headers"]).json()
    assert listed["total"] == 1
