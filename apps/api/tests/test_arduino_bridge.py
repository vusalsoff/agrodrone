"""Unit & API integration tests for the ESP32-CAM -> AgroDrone AI -> Arduino UNO Serial Bridge."""

from __future__ import annotations

import json
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from agrodrone_gateway.arduino_bridge import (
    ArduinoBridgeConfig,
    ArduinoBridgeRunner,
    SerialConnectionError,
    SerialPortLock,
    SerialPortLockError,
    evaluate_detection_decision,
)
from agrodrone_gateway.client import GatewayApiClient
from agrodrone_gateway.config import GatewayConfig
from fastapi.testclient import TestClient

from app.core.security import hash_opaque_token
from app.models.detection import DetectionItem, DetectionJob
from app.models.edge_gateway import EdgeGateway
from app.models.media import MediaAsset
from app.models.user import User


class _FakeSerialTransport:
    def __init__(self, *, fail_open: bool = False, fail_write_once: bool = False) -> None:
        self.fail_open = fail_open
        self.fail_write_once = fail_write_once
        self._open = False
        self.commands: list[bytes] = []
        self.open_calls = 0

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self.open_calls += 1
        if self.fail_open:
            raise SerialConnectionError("COM15 unavailable")
        self._open = True

    def close(self) -> None:
        self._open = False

    def write_command(self, cmd: bytes) -> None:
        if not self._open:
            raise SerialConnectionError("COM15 not open")
        if self.fail_write_once:
            self.fail_write_once = False
            self._open = False
            raise SerialConnectionError("USB cable momentarily disconnected")
        self.commands.append(cmd)


def test_evaluate_detection_decision_states() -> None:
    base = {
        "has_result": True,
        "job_id": str(uuid.uuid4()),
        "status": "completed",
        "age_seconds": 0.4,
        "ai_inference_enabled": True,
        "camera_reachable": True,
        "detections": [{"label": "person", "confidence": 0.82}],
    }

    # 1. Target class above threshold -> '1'
    state, cmd, matched, _ = evaluate_detection_decision(
        base,
        pipeline_healthy=True,
        camera_healthy=True,
        require_camera_healthy=True,
        target_classes=("person", "cow"),
        confidence_threshold=0.35,
        max_result_age_seconds=5.0,
    )
    assert state == "DETECTED"
    assert cmd == b"1"
    assert len(matched) == 1

    # 2. Target class below confidence threshold -> '0'
    state, cmd, matched, _ = evaluate_detection_decision(
        {**base, "detections": [{"label": "person", "confidence": 0.20}]},
        pipeline_healthy=True,
        camera_healthy=True,
        require_camera_healthy=True,
        target_classes=("person",),
        confidence_threshold=0.35,
        max_result_age_seconds=5.0,
    )
    assert state == "CLEAR"
    assert cmd == b"0"
    assert matched == []

    # 3. Non-target class only -> '0'
    state, cmd, _, _ = evaluate_detection_decision(
        {**base, "detections": [{"label": "chair", "confidence": 0.90}]},
        pipeline_healthy=True,
        camera_healthy=True,
        require_camera_healthy=True,
        target_classes=("person", "cow"),
        confidence_threshold=0.35,
        max_result_age_seconds=5.0,
    )
    assert state == "CLEAR"
    assert cmd == b"0"

    # 4. Stale detection -> UNAVAILABLE (never reuse stale '1' or send '0')
    state, cmd, _, reason = evaluate_detection_decision(
        {**base, "age_seconds": 8.5},
        pipeline_healthy=True,
        camera_healthy=True,
        require_camera_healthy=True,
        target_classes=("person",),
        confidence_threshold=0.35,
        max_result_age_seconds=5.0,
    )
    assert state == "UNAVAILABLE"
    assert cmd is None
    assert "stale_result" in reason

    # 5. Unprocessed / queued / failed frame -> UNAVAILABLE (never send '0')
    for bad_status in ("queued", "processing", "failed", "cancelled"):
        state, cmd, _, _ = evaluate_detection_decision(
            {**base, "status": bad_status},
            pipeline_healthy=True,
            camera_healthy=True,
            require_camera_healthy=True,
            target_classes=("person",),
            confidence_threshold=0.35,
            max_result_age_seconds=5.0,
        )
        assert state == "UNAVAILABLE"
        assert cmd is None

    # 6. Network / camera failure -> UNAVAILABLE (never send '0')
    for pipe_ok, cam_ok in ((False, True), (True, False)):
        state, cmd, _, _ = evaluate_detection_decision(
            base if pipe_ok else None,
            pipeline_healthy=pipe_ok,
            camera_healthy=cam_ok,
            require_camera_healthy=True,
            target_classes=("person",),
            confidence_threshold=0.35,
            max_result_age_seconds=5.0,
        )
        assert state == "UNAVAILABLE"
        assert cmd is None


def test_serial_port_lock_prevents_concurrent_access(tmp_path: Path) -> None:
    lock1 = SerialPortLock("COM15", lock_dir=tmp_path)
    lock2 = SerialPortLock("COM15", lock_dir=tmp_path)

    lock1.acquire()
    try:
        with pytest.raises(SerialPortLockError):
            lock2.acquire()
    finally:
        lock1.release()

    # After release, lock2 can acquire cleanly
    lock2.acquire()
    lock2.release()


def test_runner_heartbeat_reconnect_and_stale_safety(tmp_path: Path) -> None:
    state_box: dict[str, object] = {
        "latest": {
            "has_result": True,
            "job_id": str(uuid.uuid4()),
            "status": "completed",
            "age_seconds": 0.2,
            "ai_inference_enabled": True,
            "camera_reachable": True,
            "detections": [{"label": "cow", "confidence": 0.78}],
        },
        "api_down": False,
        "cam_down": False,
    }

    def api_handler(request: httpx.Request) -> httpx.Response:
        if state_box["api_down"]:
            return httpx.Response(503, json={"detail": "unavailable"})
        if request.url.path == "/api/v1/gateway/snapshots":
            return httpx.Response(201, json={"id": str(uuid.uuid4())})
        if request.url.path == "/api/v1/gateway/latest-detection":
            return httpx.Response(200, json=state_box["latest"])
        return httpx.Response(404)

    def cam_handler(_request: httpx.Request) -> httpx.Response:
        if state_box["cam_down"]:
            raise httpx.ConnectError("ESP32-CAM unreachable")
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0FAKE_JPEG\xff\xd9")

    cfg = ArduinoBridgeConfig(
        api_base_url="http://127.0.0.1:8000",
        gateway_token="agw_test_token_12345",
        serial_port="COM15",
        baudrate=9600,
        target_classes=("person", "cow"),
        confidence_threshold=0.35,
        heartbeat_interval_seconds=0.5,
        max_result_age_seconds=5.0,
        serial_reconnect_interval_seconds=0.5,
        esp32_capture_url="http://192.168.4.1/capture",
        capture_interval_seconds=0.5,
        status_file=tmp_path / "status.json",
        lock_dir=tmp_path,
    )
    gw_client = GatewayApiClient(
        GatewayConfig(api_base_url=cfg.api_base_url, gateway_token=cfg.gateway_token),
        transport=httpx.MockTransport(api_handler),
    )
    fake_serial = _FakeSerialTransport(fail_write_once=True)
    runner = ArduinoBridgeRunner(
        cfg,
        api_client=gw_client,
        serial_transport=fake_serial,
        camera_transport=httpx.MockTransport(cam_handler),
    )

    # Step 1: initial write fails -> serial disconnects -> state UNAVAILABLE
    st1 = runner.step(now_mono=10.0)
    assert st1.current_state == "UNAVAILABLE"
    assert st1.serial_connected is False
    assert fake_serial.commands == []

    # Step 2: auto-reconnect succeeds -> sends b"1" for cow detection
    st2 = runner.step(now_mono=11.0)
    assert st2.current_state == "DETECTED"
    assert st2.serial_connected is True
    assert fake_serial.commands == [b"1"]
    assert fake_serial.open_calls == 2
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["current_state"] == "DETECTED"

    # Step 3: fresh frame with no target -> sends b"0"
    state_box["latest"] = {
        **dict(state_box["latest"]),  # type: ignore[arg-type]
        "detections": [],
    }
    st3 = runner.step(now_mono=12.0)
    assert st3.current_state == "CLEAR"
    assert fake_serial.commands == [b"1", b"0"]

    # Step 4: camera drops -> UNAVAILABLE, NO command sent (lets Arduino 3s timeout trigger)
    state_box["cam_down"] = True
    st4 = runner.step(now_mono=13.0)
    assert st4.current_state == "UNAVAILABLE"
    assert st4.camera_healthy is False
    assert fake_serial.commands == [b"1", b"0"]


def test_gateway_latest_detection_endpoint(client: TestClient, db_session) -> None:
    user = User(
        email="arduino_gw@agrodrone.local",
        full_name="Arduino Bridge",
        password_hash="hashed",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    raw_token = "agw_" + secrets.token_urlsafe(24)
    gw = EdgeGateway(
        owner_id=user.id,
        name="ESP32-CAM Arduino Gateway",
        gateway_identifier=f"gw-arduino-{uuid.uuid4().hex[:8]}",
        credential_prefix=raw_token[:12],
        credential_hash=hash_opaque_token(raw_token),
        status="active",
        camera_reachable=True,
        last_heartbeat_at=datetime.now(UTC),
    )
    db_session.add(gw)
    db_session.flush()

    def _headers() -> dict[str, str]:
        return {
            "X-Gateway-Token": raw_token,
            "X-Gateway-Timestamp": f"{time.time():.3f}",
            "X-Gateway-Nonce": secrets.token_hex(16),
        }

    # Unauthenticated request is rejected
    unauth = client.get("/api/v1/gateway/latest-detection")
    assert unauth.status_code == 401

    # No jobs yet
    res_empty = client.get("/api/v1/gateway/latest-detection", headers=_headers())
    assert res_empty.status_code == 200
    assert res_empty.json()["has_result"] is False
    assert res_empty.json()["camera_reachable"] is True

    # Add a completed job with a fresh detection
    asset = MediaAsset(
        uploaded_by=user.id,
        media_type="image",
        upload_status="uploaded",
        storage_backend="local",
        storage_key="test/frame.jpg",
        safe_filename="frame.jpg",
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        byte_size=128,
        sha256="0" * 64,
        geo_source="none",
    )
    db_session.add(asset)
    db_session.flush()

    now = datetime.now(UTC)
    job = DetectionJob(
        owner_id=user.id,
        media_asset_id=asset.id,
        detection_mode="general",
        model_id="yolov8n-coco-general",
        status="completed",
        progress_percent=100,
        media_type="image",
        model_name="YOLOv8n",
        model_version="8.0.0",
        dataset_scope="MS COCO 2017",
        confidence_threshold=0.35,
        completed_at=now - timedelta(seconds=1),
    )
    db_session.add(job)
    db_session.flush()
    db_session.add(
        DetectionItem(
            job_id=job.id,
            class_id=0,
            label="person",
            confidence=0.91,
            bbox_x1=0.1,
            bbox_y1=0.1,
            bbox_x2=0.5,
            bbox_y2=0.8,
        )
    )
    db_session.commit()

    res = client.get("/api/v1/gateway/latest-detection", headers=_headers())
    assert res.status_code == 200
    data = res.json()
    assert data["has_result"] is True
    assert data["status"] == "completed"
    assert data["age_seconds"] < 5.0
    assert data["detections"] == [{"label": "person", "confidence": pytest.approx(0.91)}]
