"""Comprehensive Phase 4 tests: Gateway auth, rotation, revocation, replay guard, MJPEG, spool, relay & E2E AI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from agrodrone_gateway.client import GatewayApiClient
from agrodrone_gateway.config import GatewayConfig
from agrodrone_gateway.mjpeg import FrameValidationError, iter_mjpeg_frames, validate_jpeg_frame
from agrodrone_gateway.runner import EdgeGatewayRunner
from agrodrone_gateway.spool import OfflineSnapshotSpool
from agrovision_worker.engine import RawDetectionBox
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.edge_gateway import EdgeGateway, StreamSession
from app.services import vision
from tests.media_fixtures import make_jpeg


def _mjpeg_payload(frames: list[bytes], boundary: bytes = b"frame") -> bytes:
    parts: list[bytes] = []
    for frame in frames:
        parts.append(
            b"--"
            + boundary
            + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
            + str(len(frame)).encode("ascii")
            + b"\r\n\r\n"
            + frame
            + b"\r\n"
        )
    parts.append(b"--" + boundary + b"--\r\n")
    return b"".join(parts)


def test_mjpeg_frame_parser_and_resource_limits() -> None:
    f1 = make_jpeg(64, 48)
    f2 = make_jpeg(80, 60)
    raw = _mjpeg_payload([f1, f2])

    # Split across arbitrary odd-sized chunks to test boundary reassembly
    chunks = [raw[i : i + 17] for i in range(0, len(raw), 17)]
    extracted = list(iter_mjpeg_frames(iter(chunks), max_frame_bytes=64 * 1024))
    assert extracted == [f1, f2]

    # Oversized frame rejected
    with pytest.raises(FrameValidationError):
        validate_jpeg_frame(f1, max_frame_bytes=50)

    # Non-JPEG rejected
    with pytest.raises(FrameValidationError):
        validate_jpeg_frame(b"<html>not-jpeg</html>", max_frame_bytes=64 * 1024)


def test_offline_spool_enqueue_quota_and_retries(tmp_path: Path) -> None:
    spool = OfflineSnapshotSpool(tmp_path / "spool", quota_bytes=5000)
    j1 = make_jpeg(32, 32)
    j2 = make_jpeg(32, 32)

    s1 = spool.enqueue(j1, filename="snap1.jpg", notes="offline1")
    assert spool.stats()[0] == 1
    assert len(spool.list_pending()) == 1

    # Exceeding quota evicts oldest cleanly
    big_spool = OfflineSnapshotSpool(tmp_path / "small_spool", quota_bytes=len(j1) + 10)
    big_spool.enqueue(j1, filename="old.jpg")
    big_spool.enqueue(j2, filename="new.jpg")
    assert big_spool.stats()[0] == 1
    assert big_spool.list_pending()[0].filename == "new.jpg"

    # Retry limit stops returning permanently failing items
    spool.record_failure(s1.id, "timeout")
    spool.record_failure(s1.id, "timeout")
    assert len(spool.list_pending(max_attempts=2)) == 0

    spool.mark_uploaded(s1.id)
    assert spool.stats() == (0, 0)


def test_gateway_enrollment_rotation_revocation_replay_and_ownership(
    client: TestClient,
    db_session: Session,
    register_user: Callable[..., dict[str, Any]],
) -> None:
    _admin = register_user("admin@agrodrone.dev")
    owner = register_user("owner@agrodrone.dev", role="agronomist")
    other = register_user("other@agrodrone.dev", role="operator")

    dev = client.post(
        "/api/v1/devices",
        headers=owner["headers"],
        json={
            "name": "ESP32-CAM Field #1",
            "device_type": "camera_module",
            "device_identifier": "ESP32-GW-01",
            "hardware_model": "AI Thinker ESP32-CAM (OV2640)",
            "connectivity_mode": "isolated_ap",
            "local_ssid": "agroDrone",
            "local_endpoint_url": "http://192.168.4.1",
        },
    ).json()

    enrolled = client.post(
        "/api/v1/gateway/enroll",
        headers=owner["headers"],
        json={
            "name": "Field Laptop Gateway",
            "gateway_identifier": "gw-laptop-01",
            "device_id": dev["id"],
            "deployment_mode": "local_dev",
        },
    )
    assert enrolled.status_code == 201
    token_v1 = enrolled.json()["gateway_token"]
    gw_id = enrolled.json()["gateway"]["id"]
    assert token_v1.startswith("agw_")
    assert enrolled.json()["gateway"]["is_live"] is False

    # Listing gateways never exposes the secret token
    listed = client.get("/api/v1/gateway", headers=owner["headers"])
    assert listed.status_code == 200
    assert token_v1 not in listed.text

    # Cross-user cannot inspect, rotate, or revoke owner's gateway
    assert client.get(f"/api/v1/gateway/{gw_id}/diagnostics", headers=other["headers"]).status_code == 403
    assert client.post(f"/api/v1/gateway/{gw_id}/rotate", headers=other["headers"]).status_code == 403
    assert client.post(f"/api/v1/gateway/{gw_id}/revoke", headers=other["headers"]).status_code == 403

    # Heartbeat with valid token marks gateway live
    hb = client.post(
        "/api/v1/gateway/heartbeat",
        headers={"X-Gateway-Token": token_v1, "X-Gateway-Nonce": "nonce-1"},
        json={"camera_reachable": True, "camera_fps": 2.4, "queue_depth": 0},
    )
    assert hb.status_code == 200

    # Replay protection: reusing same nonce fails with 401
    replay = client.post(
        "/api/v1/gateway/heartbeat",
        headers={"X-Gateway-Token": token_v1, "X-Gateway-Nonce": "nonce-1"},
        json={"camera_reachable": True},
    )
    assert replay.status_code == 401

    # Stale timestamp fails with 401
    stale = client.post(
        "/api/v1/gateway/heartbeat",
        headers={"X-Gateway-Token": token_v1, "X-Gateway-Timestamp": "1000000.0"},
        json={"camera_reachable": True},
    )
    assert stale.status_code == 401

    # Credential rotation invalidates v1 and activates v2
    rotated = client.post(f"/api/v1/gateway/{gw_id}/rotate", headers=owner["headers"])
    assert rotated.status_code == 200
    token_v2 = rotated.json()["gateway_token"]
    assert token_v2 != token_v1

    assert (
        client.post(
            "/api/v1/gateway/heartbeat",
            headers={"X-Gateway-Token": token_v1},
            json={"camera_reachable": True},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/gateway/heartbeat",
            headers={"X-Gateway-Token": token_v2},
            json={"camera_reachable": True},
        ).status_code
        == 200
    )

    # Heartbeat expiry: backdating last_heartbeat_at marks gateway offline (is_live=False)
    gw_row = db_session.get(EdgeGateway, __import__("uuid").UUID(gw_id))
    gw_row.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()

    diag = client.get(f"/api/v1/gateway/{gw_id}/diagnostics", headers=owner["headers"]).json()
    assert diag["gateway"]["is_live"] is False
    assert diag["gateway"]["heartbeat_age_seconds"] >= 290

    # Revoke invalidates token_v2 immediately
    revoked = client.post(f"/api/v1/gateway/{gw_id}/revoke", headers=owner["headers"])
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert (
        client.post(
            "/api/v1/gateway/heartbeat",
            headers={"X-Gateway-Token": token_v2},
            json={"camera_reachable": True},
        ).status_code
        == 401
    )


def test_stream_session_relay_expiry_and_end_to_end_mjpeg_to_ai(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
    tmp_path: Path,
    register_user: Callable[..., dict[str, Any]],
) -> None:
    test_settings.ai_inference_enabled = True
    vision.set_test_predictors(
        lambda rgb, _c: [RawDetectionBox(19, "cow", 0.91, 4, 4, 48, 40)],
        None,
    )

    owner = register_user("e2e@agrodrone.dev", role="agronomist")
    gw = client.post(
        "/api/v1/gateway/enroll",
        headers=owner["headers"],
        json={
            "name": "E2E Gateway",
            "gateway_identifier": "gw-e2e-01",
            "deployment_mode": "local_dev",
        },
    ).json()
    gw_id = gw["gateway"]["id"]
    token = gw["gateway_token"]

    # Start bounded stream session
    sess_res = client.post(
        f"/api/v1/gateway/{gw_id}/stream/start",
        headers=owner["headers"],
        json={"target_fps": 2.0, "max_frame_bytes": 262144, "duration_seconds": 120},
    )
    assert sess_res.status_code == 201
    sess_id = sess_res.json()["id"]

    # Before first frame arrives, /stream/latest returns 204
    assert client.get(f"/api/v1/gateway/{gw_id}/stream/latest", headers=owner["headers"]).status_code == 204

    # Simulated ESP32-CAM MJPEG HTTP source via httpx.MockTransport
    cam_jpeg = make_jpeg(96, 64)
    mjpeg_bytes = _mjpeg_payload([cam_jpeg, cam_jpeg])

    def _mock_camera(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"},
                content=mjpeg_bytes,
            )
        return httpx.Response(404)

    class _TestClientApiBridge(GatewayApiClient):
        def __init__(self, cfg: GatewayConfig) -> None:
            self._cfg = cfg
            self._client = client  # type: ignore[assignment]

        def close(self) -> None:
            pass

    cfg = GatewayConfig(
        api_base_url="http://testserver",
        gateway_token=token,
        esp32_stream_url="http://192.168.4.1:81/stream",
        offline_spool_dir=tmp_path / "gw_spool",
        target_fps=5.0,
    )
    runner = EdgeGatewayRunner(
        cfg,
        api_client=_TestClientApiBridge(cfg),
        camera_transport=httpx.MockTransport(_mock_camera),
    )

    # 1. Heartbeat notifies gateway that stream_active=True
    runner._send_heartbeat()
    assert runner.stream_active is True

    # 2. Gateway reads MJPEG stream, pushes live frame & uploads snapshot
    processed = runner.run_once_from_stream(max_frames=1, save_snapshot=True)
    assert processed == 1

    # 3. Frontend fetches relayed JPEG frame from /stream/latest
    relayed = client.get(f"/api/v1/gateway/{gw_id}/stream/latest", headers=owner["headers"])
    assert relayed.status_code == 200
    assert relayed.content == cam_jpeg

    # 4. Snapshot appears in gateway snapshot gallery & triggers YOLOv8n analysis
    snaps = client.get(f"/api/v1/gateway/{gw_id}/snapshots", headers=owner["headers"]).json()
    assert snaps["total"] == 1
    media_id = snaps["items"][0]["id"]

    job = client.post(
        f"/api/v1/gateway/snapshots/{media_id}/analyze",
        headers=owner["headers"],
        json={"model_id": "yolov8n-coco-general", "confidence_threshold": 0.35},
    ).json()
    assert job["status"] == "completed"
    assert job["summary_json"]["class_counts"] == {"cow": 1}

    # 5. Stream expiration blocks further frames
    sess_row = db_session.get(StreamSession, __import__("uuid").UUID(sess_id))
    sess_row.expires_at = datetime.now(UTC) - timedelta(seconds=10)
    db_session.commit()

    assert client.get(f"/api/v1/gateway/{gw_id}/stream/latest", headers=owner["headers"]).status_code == 409
    assert (
        client.post(
            "/api/v1/gateway/stream/frame",
            headers={"X-Gateway-Token": token},
            files={"file": ("f.jpg", cam_jpeg, "image/jpeg")},
        ).status_code
        == 409
    )

    # 6. Camera connection failure leaves camera_reachable=False cleanly
    failing_runner = EdgeGatewayRunner(
        cfg,
        api_client=_TestClientApiBridge(cfg),
        camera_transport=httpx.MockTransport(lambda _req: httpx.Response(503)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        failing_runner.run_once_from_stream(max_frames=1)
    assert failing_runner.camera_reachable is False

    vision.set_test_predictors(None, None)
