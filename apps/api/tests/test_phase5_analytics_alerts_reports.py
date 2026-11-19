"""Phase 5 tests: Smart Analytics, Alert Rules, Notifications, Reporting, CSV Safety & Map Integrity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    DetectionItem,
    DetectionJob,
    Device,
    EdgeGateway,
    Field,
    MediaAsset,
    Mission,
)
from app.services.gateway_relay import generate_gateway_credential


def _register_and_login(
    client: TestClient, *, email: str, role: str = "agronomist"
) -> tuple[str, str]:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0].title(),
            "password": "StrongPassword!123",
            "role": role,
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]
    client.cookies.clear()
    return token, user_id


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_analytics_correctness_video_dedup_and_missing_data(
    client: TestClient, db_session: Session
) -> None:
    token, user_id_str = _register_and_login(client, email="analytics_owner@agrodrone.io")
    owner_id = uuid.UUID(user_id_str)

    # Empty state first: zero fake stats
    empty_res = client.get("/api/v1/analytics/overview", headers=_auth_headers(token))
    assert empty_res.status_code == 200, empty_res.text
    empty_data = empty_res.json()
    assert empty_data["jobs_summary"]["total_jobs"] == 0
    assert empty_data["detections_summary"]["raw_detection_items"] == 0
    assert empty_data["class_distribution"] == []
    assert empty_data["detection_trends"] == []

    field = Field(
        owner_id=owner_id,
        name="North Barley Plot",
        code="NBP-01",
        crop_type="Barley",
        area_hectares=4.25,
    )
    db_session.add(field)
    db_session.flush()

    mission = Mission(
        owner_id=owner_id,
        field_id=field.id,
        title="Morning Survey",
        status="completed",
    )
    db_session.add(mission)
    db_session.flush()

    video_asset = MediaAsset(
        uploaded_by=owner_id,
        field_id=field.id,
        mission_id=mission.id,
        media_type="video",
        storage_backend="local",
        storage_key="tests/video-1.mp4",
        original_filename="video-1.mp4",
        mime_type="video/mp4",
        byte_size=1024,
        sha256="a" * 64,
    )
    db_session.add(video_asset)
    db_session.flush()

    # Sampled video job with 3 repeated 'bird' detections across 3 frames + 1 'person'
    job = DetectionJob(
        owner_id=owner_id,
        field_id=field.id,
        mission_id=mission.id,
        media_asset_id=video_asset.id,
        detection_mode="general",
        model_id="yolov8n-coco-general",
        status="completed",
        media_type="video",
        model_name="YOLOv8n",
        model_version="8.4",
        dataset_scope="COCO 80-class general baseline",
        inference_ms=240,
    )
    db_session.add(job)
    db_session.flush()

    for frame_idx, review in [(0, "confirmed"), (1, "unreviewed"), (2, "unreviewed")]:
        db_session.add(
            DetectionItem(
                job_id=job.id,
                class_id=14,
                label="bird",
                confidence=0.82,
                bbox_x1=10,
                bbox_y1=10,
                bbox_x2=50,
                bbox_y2=50,
                frame_index=frame_idx,
                review_status=review,
            )
        )
    db_session.add(
        DetectionItem(
            job_id=job.id,
            class_id=0,
            label="person",
            confidence=0.91,
            bbox_x1=20,
            bbox_y1=20,
            bbox_x2=80,
            bbox_y2=120,
            frame_index=0,
            review_status="rejected",
        )
    )
    db_session.commit()

    res = client.get("/api/v1/analytics/overview", headers=_auth_headers(token))
    assert res.status_code == 200
    data = res.json()
    assert data["jobs_summary"]["total_jobs"] == 1
    assert data["jobs_summary"]["completed_jobs"] == 1
    assert data["jobs_summary"]["avg_inference_ms"] == 240.0
    # 4 raw items, but only 2 unique (job_id, label) pairs -> prevents video frame double counting!
    assert data["detections_summary"]["raw_detection_items"] == 4
    assert data["detections_summary"]["unique_job_class_occurrences"] == 2
    assert data["detections_summary"]["human_confirmed_count"] == 1
    assert data["detections_summary"]["human_rejected_count"] == 1
    assert data["detections_summary"]["unreviewed_count"] == 2
    assert len(data["field_summaries"]) == 1
    assert data["field_summaries"][0]["unique_job_class_occurrences"] == 2


def test_alert_rule_validation_trigger_deduplication_and_notifications(
    client: TestClient, db_session: Session
) -> None:
    token, user_id_str = _register_and_login(client, email="alerts_user@agrodrone.io")
    owner_id = uuid.UUID(user_id_str)

    # Reject unsupported specialized pest/wildlife/disease classes
    bad_rule = client.post(
        "/api/v1/alert-rules",
        headers=_auth_headers(token),
        json={
            "name": "Snake Alert",
            "severity": "critical",
            "trigger_type": "yolo_class_detected",
            "target_classes": ["snake", "crop_blight"],
        },
    )
    assert bad_rule.status_code == 422

    # Valid rule on supported COCO class
    good_rule = client.post(
        "/api/v1/alert-rules",
        headers=_auth_headers(token),
        json={
            "name": "Bird Activity Rule",
            "severity": "warning",
            "trigger_type": "yolo_class_detected",
            "target_classes": ["bird"],
            "min_confidence": 0.6,
            "cooldown_minutes": 30,
        },
    )
    assert good_rule.status_code == 201, good_rule.text
    rule_id = good_rule.json()["id"]

    # Create job + detection and evaluate
    asset = MediaAsset(
        uploaded_by=owner_id,
        media_type="image",
        storage_backend="local",
        storage_key="tests/bird-img.jpg",
        original_filename="bird-img.jpg",
        mime_type="image/jpeg",
        byte_size=512,
        sha256="b" * 64,
    )
    db_session.add(asset)
    db_session.flush()
    job = DetectionJob(
        owner_id=owner_id,
        media_asset_id=asset.id,
        model_id="yolov8n-coco-general",
        status="completed",
        media_type="image",
        model_name="YOLOv8n",
        model_version="8.4",
        dataset_scope="COCO",
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        DetectionItem(
            job_id=job.id,
            class_id=14,
            label="bird",
            confidence=0.88,
            bbox_x1=1,
            bbox_y1=1,
            bbox_x2=10,
            bbox_y2=10,
        )
    )
    db_session.commit()

    from app.core.config import get_settings
    from app.services.alerts import evaluate_detection_job_event

    first = evaluate_detection_job_event(db_session, get_settings(), job.id)
    db_session.commit()
    assert len(first) == 1

    # Re-evaluating same job must deduplicate (no second alert)
    second = evaluate_detection_job_event(db_session, get_settings(), job.id)
    db_session.commit()
    assert len(second) == 0

    alerts_res = client.get("/api/v1/alerts", headers=_auth_headers(token))
    assert alerts_res.status_code == 200
    assert alerts_res.json()["total"] == 1
    alert_id = alerts_res.json()["items"][0]["id"]
    assert alerts_res.json()["items"][0]["rule_id"] == rule_id

    # In-app notification created & unread count == 1
    unread = client.get("/api/v1/notifications/unread-count", headers=_auth_headers(token))
    assert unread.status_code == 200
    assert unread.json()["unread_count"] == 1

    notifs = client.get("/api/v1/notifications", headers=_auth_headers(token))
    assert notifs.status_code == 200
    notif_id = notifs.json()["items"][0]["id"]

    mark = client.post(f"/api/v1/notifications/{notif_id}/read", headers=_auth_headers(token))
    assert mark.status_code == 200
    assert mark.json()["is_read"] is True

    # Honest SMTP unavailable check
    pref = client.get("/api/v1/notifications/preferences", headers=_auth_headers(token))
    assert pref.status_code == 200
    assert pref.json()["email_available"] is False

    bad_pref = client.patch(
        "/api/v1/notifications/preferences",
        headers=_auth_headers(token),
        json={"email_enabled": True, "email_address": "ops@agrodrone.io"},
    )
    assert bad_pref.status_code == 422

    # Acknowledge & Resolve alert
    ack = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=_auth_headers(token))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    res_alert = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        headers=_auth_headers(token),
        json={"resolution_notes": "Verified by operator."},
    )
    assert res_alert.status_code == 200
    assert res_alert.json()["status"] == "resolved"


def test_gateway_offline_ttl_alert_and_connectivity_history(
    client: TestClient, db_session: Session
) -> None:
    token, user_id_str = _register_and_login(client, email="gw_alert@agrodrone.io")
    owner_id = uuid.UUID(user_id_str)

    rule_res = client.post(
        "/api/v1/alert-rules",
        headers=_auth_headers(token),
        json={
            "name": "ESP32 Gateway Offline",
            "severity": "critical",
            "trigger_type": "gateway_offline_ttl",
            "cooldown_minutes": 10,
        },
    )
    assert rule_res.status_code == 201

    dev = Device(
        owner_id=owner_id,
        name="ESP32-CAM Field Unit",
        device_type="esp32_cam",
        hardware_model="AI Thinker ESP32-CAM",
        device_identifier="esp32-cam-offline-test",
    )
    db_session.add(dev)
    db_session.flush()

    _, prefix, token_hash = generate_gateway_credential()
    gw = EdgeGateway(
        owner_id=owner_id,
        device_id=dev.id,
        name="Field Gateway 1",
        gateway_identifier="gw-offline-01",
        deployment_mode="local_dev",
        credential_prefix=prefix,
        credential_hash=token_hash,
        status="active",
        last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(gw)
    db_session.commit()

    eval_res = client.post("/api/v1/alerts/evaluate-gateways", headers=_auth_headers(token))
    assert eval_res.status_code == 200
    assert eval_res.json()["offline_detected"] == 1
    assert eval_res.json()["alerts_created"] == 1

    # Second call must deduplicate alert
    eval_res2 = client.post("/api/v1/alerts/evaluate-gateways", headers=_auth_headers(token))
    assert eval_res2.status_code == 200
    assert eval_res2.json()["alerts_created"] == 0

    analytics = client.get("/api/v1/analytics/overview", headers=_auth_headers(token)).json()
    assert len(analytics["device_connectivity"]) == 1
    assert analytics["device_connectivity"][0]["offline_events"] == 1


def test_reports_export_pdf_csv_formula_injection_json_and_isolation(
    client: TestClient, db_session: Session
) -> None:
    token_a, user_a_str = _register_and_login(client, email="report_a@agrodrone.io")
    token_b, _ = _register_and_login(client, email="report_b@agrodrone.io")
    user_a = uuid.UUID(user_a_str)

    # Create a field with a CSV formula-injection payload in name
    f = Field(
        owner_id=user_a,
        name="=CMD('calc')-Plot",
        code="+DANGEROUS",
        crop_type="@Wheat",
        area_hectares=2.5,
    )
    db_session.add(f)
    db_session.commit()

    # CSV export for User A sanitizes formula characters
    csv_res = client.get(
        "/api/v1/reports/export?report_type=field_analysis&format=csv",
        headers=_auth_headers(token_a),
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    csv_text = csv_res.text
    assert "'=CMD('calc')-Plot" in csv_text
    assert "'+DANGEROUS" in csv_text
    assert "'@Wheat" in csv_text

    # PDF export produces valid %PDF binary
    pdf_res = client.get(
        "/api/v1/reports/export?report_type=field_analysis&format=pdf",
        headers=_auth_headers(token_a),
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    # JSON export
    json_res = client.get(
        "/api/v1/reports/export?report_type=ai_detection&format=json",
        headers=_auth_headers(token_a),
    )
    assert json_res.status_code == 200
    assert "methodological_limitations" in json_res.json()

    # Cross-user isolation: User B sees 0 fields in preview/export
    b_preview = client.get(
        "/api/v1/reports/preview?report_type=field_analysis",
        headers=_auth_headers(token_b),
    )
    assert b_preview.status_code == 200
    assert b_preview.json()["summary_metrics"]["fields_count"] == 0
    assert b_preview.json()["rows"] == []


def test_map_analytics_coordinate_integrity(client: TestClient, db_session: Session) -> None:
    token, user_id_str = _register_and_login(client, email="map_integrity@agrodrone.io")
    owner_id = uuid.UUID(user_id_str)

    # Asset WITHOUT GPS must NEVER be fabricated onto the map
    no_gps_asset = MediaAsset(
        uploaded_by=owner_id,
        media_type="image",
        storage_backend="local",
        storage_key="tests/no-gps.jpg",
        original_filename="no-gps.jpg",
        mime_type="image/jpeg",
        byte_size=400,
        sha256="c" * 64,
        geo_source="none",
    )
    # Asset WITH verified EXIF GPS SHOULD appear
    gps_asset = MediaAsset(
        uploaded_by=owner_id,
        media_type="image",
        storage_backend="local",
        storage_key="tests/with-gps.jpg",
        original_filename="with-gps.jpg",
        mime_type="image/jpeg",
        byte_size=400,
        sha256="d" * 64,
        geo_lat=40.4093,
        geo_lng=49.8671,
        geo_source="exif",
    )
    db_session.add_all([no_gps_asset, gps_asset])
    db_session.flush()

    for asset in (no_gps_asset, gps_asset):
        j = DetectionJob(
            owner_id=owner_id,
            media_asset_id=asset.id,
            model_id="yolov8n-coco-general",
            status="completed",
            media_type="image",
            model_name="YOLOv8n",
            model_version="8.4",
            dataset_scope="COCO",
        )
        db_session.add(j)
        db_session.flush()
        db_session.add(
            DetectionItem(
                job_id=j.id,
                class_id=14,
                label="bird",
                confidence=0.77,
                bbox_x1=1,
                bbox_y1=1,
                bbox_x2=10,
                bbox_y2=10,
            )
        )
    db_session.commit()

    res = client.get("/api/v1/analytics/map-summary", headers=_auth_headers(token))
    assert res.status_code == 200
    data = res.json()
    assert data["gps_telemetry_available"] is False
    assert len(data["verified_detection_points"]) == 1
    assert data["verified_detection_points"][0]["original_filename"] == "with-gps.jpg"
    assert data["verified_detection_points"][0]["geo_lat"] == 40.4093
    assert data["verified_detection_points"][0]["geo_lng"] == 49.8671
