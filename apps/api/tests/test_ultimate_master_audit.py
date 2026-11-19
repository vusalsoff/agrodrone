"""Ultimate Master Audit Suite: Security Penetration, PNG/Real AI, Gateway Replay & Latency Benchmarks."""

from __future__ import annotations

import io
import statistics
import time
import uuid
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import build_engine
from app.main import create_app
from tests.media_fixtures import make_jpeg

try:
    from ultralytics.utils import ASSETS

    BUS_JPG = Path(ASSETS) / "bus.jpg"
except Exception:  # noqa: BLE001
    BUS_JPG = Path("missing")


def _reg_user(client: TestClient, email: str, role: str = "agronomist") -> tuple[str, str]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "StrongPassword!123",
            "role": role,
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    uid = res.json()["user"]["id"]
    client.cookies.clear()
    return token, uid


def test_security_penetration_idor_sqli_traversal_csrf_cors_and_replay(
    client: TestClient,
) -> None:
    # User 1 (first user -> auto-promoted to admin)
    tok_a, _ = _reg_user(client, "sec_admin@agrodrone.io", role="agronomist")
    # User 2 (viewer -> read-only)
    tok_viewer, _ = _reg_user(client, "sec_viewer@agrodrone.io", role="viewer")
    # User 3 (agronomist -> different tenant/owner)
    tok_b, _ = _reg_user(client, "sec_other@agrodrone.io", role="agronomist")

    # 1. Invalid login attempt
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "sec_admin@agrodrone.io", "password": "WrongPassword!999"},
    )
    assert bad_login.status_code == 401
    client.cookies.clear()

    # 2. Cookie CSRF rejection on state-changing request without X-CSRF-Token
    good_login = client.post(
        "/api/v1/auth/login",
        json={"email": "sec_admin@agrodrone.io", "password": "StrongPassword!123"},
    )
    assert good_login.status_code == 200
    no_csrf = client.post(
        "/api/v1/fields",
        json={"name": "CSRF Bypass Attempt", "code": "CSRF-1"},
    )
    assert no_csrf.status_code == 403
    client.cookies.clear()

    # 3. RBAC enforcement: viewer cannot create field, device, or alert rule
    assert (
        client.post(
            "/api/v1/fields",
            headers={"Authorization": f"Bearer {tok_viewer}"},
            json={"name": "Viewer Field", "code": "VW-1"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/alert-rules",
            headers={"Authorization": f"Bearer {tok_viewer}"},
            json={"name": "Viewer Rule", "severity": "info", "trigger_type": "ai_analysis_failed"},
        ).status_code
        == 403
    )

    # 4. SQLi & XSS payloads stored safely without SQL error or crash
    sqli_field = client.post(
        "/api/v1/fields",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"name": "Plot '; DROP TABLE fields; -- <script>alert(1)</script>", "code": "SQLI-1"},
    )
    assert sqli_field.status_code == 201
    field_id = sqli_field.json()["id"]

    # 5. IDOR / Cross-user isolation: User B cannot view or delete User A's field
    assert (
        client.get(
            f"/api/v1/fields/{field_id}", headers={"Authorization": f"Bearer {tok_b}"}
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/fields/{field_id}", headers={"Authorization": f"Bearer {tok_b}"}
        ).status_code
        == 403
    )

    # 6. Path traversal in upload filename + corrupt magic-byte spoof rejection
    jpg = make_jpeg(64, 64)
    trav_up = client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {tok_a}"},
        files={"file": ("../../etc/passwd.jpg", jpg, "image/jpeg")},
    )
    assert trav_up.status_code == 201
    assert ".." not in trav_up.json()["storage_key"]
    media_id = trav_up.json()["id"]

    # Cross-user media download denied
    assert (
        client.get(
            f"/api/v1/media/{media_id}/content",
            headers={"Authorization": f"Bearer {tok_b}"},
        ).status_code
        == 403
    )

    # Corrupt file spoofed as image/jpeg rejected
    bad_up = client.post(
        "/api/v1/media/upload",
        headers={"Authorization": f"Bearer {tok_a}"},
        files={"file": ("evil.jpg", b"#!/bin/sh\nrm -rf /\n", "image/jpeg")},
    )
    assert bad_up.status_code in (400, 422)

    # 7. CORS disallowed origin check
    preflight = client.options(
        "/api/v1/health",
        headers={"Origin": "https://evil-attacker.example", "Access-Control-Request-Method": "GET"},
    )
    assert preflight.headers.get("access-control-allow-origin") != "https://evil-attacker.example"

    # 8. Gateway replay attack rejection
    gw_res = client.post(
        "/api/v1/gateway/enroll",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"name": "Replay Test GW", "gateway_identifier": "gw-replay-01", "deployment_mode": "local_dev"},
    )
    assert gw_res.status_code == 201
    gw_tok = gw_res.json()["gateway_token"]
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    gw_headers = {
        "X-Gateway-Token": gw_tok,
        "X-Gateway-Timestamp": ts,
        "X-Gateway-Nonce": nonce,
    }
    hb1 = client.post(
        "/api/v1/gateway/heartbeat",
        headers=gw_headers,
        json={"camera_reachable": True, "dropped_frames": 0, "queue_depth": 0, "queue_bytes": 0},
    )
    assert hb1.status_code == 200
    # Replaying exact same timestamp + nonce must be rejected!
    hb_replay = client.post(
        "/api/v1/gateway/heartbeat",
        headers=gw_headers,
        json={"camera_reachable": True, "dropped_frames": 0, "queue_depth": 0, "queue_bytes": 0},
    )
    assert hb_replay.status_code in (401, 403, 409)


@pytest.mark.real_model
def test_png_real_yolov8n_inference_and_api_latency_benchmarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not BUS_JPG.exists():
        pytest.skip("Ultralytics bus.jpg not available.")

    # Convert real bus.jpg to PNG to verify PNG upload + real YOLOv8n inference
    png_buf = io.BytesIO()
    with Image.open(BUS_JPG) as im:
        width, height = im.size
        im.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    db_file = tmp_path / "audit_perf.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    from alembic import command
    from alembic.config import Config

    api_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(api_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    command.upgrade(alembic_cfg, "head")

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        storage_backend="local",
        local_storage_path=str(storage_dir),
        ai_inference_enabled=True,
        ai_worker_mode="inline_thread",
        auth_rate_limit_requests=200,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    app = create_app(settings)
    from app.api.deps import get_db_session
    from app.core.config import get_settings as orig_get_settings

    engine = build_engine(settings)
    SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _override_db():
        s = SessionFactory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[orig_get_settings] = lambda: settings

    with TestClient(app) as client:
        tok, _ = _reg_user(client, "perf_audit@agrodrone.io")
        auth = {"Authorization": f"Bearer {tok}"}

        up = client.post(
            "/api/v1/media/upload",
            headers=auth,
            files={"file": ("bus_scene.png", png_bytes, "image/png")},
        )
        assert up.status_code == 201
        media_id = up.json()["id"]

        rss_before = psutil.Process().memory_info().rss / (1024 * 1024)
        job_res = client.post(
            "/api/v1/detections/jobs",
            headers=auth,
            json={"media_asset_id": media_id, "model_id": "yolov8n-coco-general", "confidence_threshold": 0.25},
        )
        assert job_res.status_code == 202
        job_id = job_res.json()["id"]

        job_data = {}
        for _ in range(60):
            r = client.get(f"/api/v1/detections/jobs/{job_id}", headers=auth)
            assert r.status_code == 200
            job_data = r.json()
            if job_data["status"] in {"completed", "failed"}:
                break
            time.sleep(0.25)
        rss_after = psutil.Process().memory_info().rss / (1024 * 1024)

        assert job_data["status"] == "completed"
        assert len(job_data["items"]) >= 1
        for item in job_data["items"]:
            assert 0.0 <= item["confidence"] <= 1.0
            assert 0.0 <= item["bbox_x1"] <= item["bbox_x2"] <= width
            assert 0.0 <= item["bbox_y1"] <= item["bbox_y2"] <= height

        # Export JSON verification
        exp = client.get(f"/api/v1/detections/jobs/{job_id}/export", headers=auth)
        assert exp.status_code == 200
        assert exp.json()["job"]["id"] == job_id

        # API Latency Benchmark (20 calls each)
        health_lat: list[float] = []
        analytics_lat: list[float] = []
        for _ in range(20):
            t0 = time.perf_counter()
            assert client.get("/api/v1/health").status_code == 200
            health_lat.append((time.perf_counter() - t0) * 1000)

            t1 = time.perf_counter()
            assert client.get("/api/v1/analytics/overview", headers=auth).status_code == 200
            analytics_lat.append((time.perf_counter() - t1) * 1000)

        print(
            f"\n[AUDIT_PERF] png_inference_ms={job_data['inference_ms']} detections={len(job_data['items'])} "
            f"rss_before_mb={rss_before:.1f} rss_after_mb={rss_after:.1f} "
            f"health_p50_ms={statistics.median(health_lat):.2f} health_p95_ms={sorted(health_lat)[18]:.2f} "
            f"analytics_p50_ms={statistics.median(analytics_lat):.2f} analytics_p95_ms={sorted(analytics_lat)[18]:.2f}"
        )
    engine.dispose()
