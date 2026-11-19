"""Phase 7 End-to-End 15-Step Workflow, Restart Persistence & Performance Benchmark."""

from __future__ import annotations

import concurrent.futures
import time
import uuid
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import build_engine
from app.main import create_app
from app.services.vision import execute_detection_job_in_session

try:
    from ultralytics.utils import ASSETS

    BUS_JPG = Path(ASSETS) / "bus.jpg"
except Exception:  # noqa: BLE001
    BUS_JPG = Path("missing")


@pytest.mark.real_model
def test_phase7_full_15_step_e2e_restart_persistence_and_benchmarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the complete 15-step user journey, restart persistence, and real CPU benchmarks."""
    db_file = tmp_path / "phase7_e2e.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Apply Alembic migrations to this fresh SQLite DB
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
        ai_worker_mode="external",
        edge_gateway_enabled=True,
        auth_rate_limit_requests=100,
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
        # 1. Register
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": "phase7_e2e@agrodrone.io",
                "full_name": "Phase Seven Lead",
                "password": "StrongPassword!123",
                "role": "agronomist",
            },
        )
        assert reg.status_code == 201, reg.text
        client.cookies.clear()

        # 2. Login securely with cookies + CSRF
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "phase7_e2e@agrodrone.io", "password": "StrongPassword!123"},
        )
        assert login.status_code == 200, login.text
        csrf = client.cookies.get("agrodrone_csrf_token")
        assert csrf
        headers = {"X-CSRF-Token": csrf}

        # 3 & 4. Create field + GeoJSON polygon
        field_res = client.post(
            "/api/v1/fields",
            headers=headers,
            json={
                "name": "Phase 7 Verification Plot",
                "code": "P7-001",
                "crop_type": "Winter Wheat",
                "boundary_geojson": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [49.85, 40.40],
                            [49.86, 40.40],
                            [49.86, 40.41],
                            [49.85, 40.41],
                            [49.85, 40.40],
                        ]
                    ],
                },
            },
        )
        assert field_res.status_code == 201, field_res.text
        field_id = field_res.json()["id"]
        assert field_res.json()["area_hectares"] > 0

        # 5. Register device
        dev_res = client.post(
            "/api/v1/devices",
            headers=headers,
            json={
                "name": "ESP32-CAM Bench Unit",
                "device_type": "camera_module",
                "hardware_model": "AI Thinker ESP32-CAM",
                "device_identifier": "esp32-p7-001",
                "assigned_field_id": field_id,
            },
        )
        assert dev_res.status_code == 201, dev_res.text
        device_id = dev_res.json()["id"]

        # 6. Create mission & transition to completed
        mission_res = client.post(
            "/api/v1/missions",
            headers=headers,
            json={
                "title": "Phase 7 Validation Survey",
                "field_id": field_id,
                "device_id": device_id,
            },
        )
        assert mission_res.status_code == 201, mission_res.text
        mission_id = mission_res.json()["id"]

        # 7. Upload real image
        if not BUS_JPG.exists():
            pytest.skip("Ultralytics sample bus.jpg not available.")
        photo_bytes = BUS_JPG.read_bytes()
        t_up0 = time.perf_counter()
        up_res = client.post(
            "/api/v1/media/upload",
            headers=headers,
            data={"field_id": field_id, "mission_id": mission_id},
            files={"file": ("scene.jpg", photo_bytes, "image/jpeg")},
        )
        upload_ms = round((time.perf_counter() - t_up0) * 1000, 2)
        assert up_res.status_code == 201, up_res.text
        media_id = up_res.json()["id"]

        # 12 (pre-configure rule before job). Alert rule on human_confirmed_detection
        rule_res = client.post(
            "/api/v1/alert-rules",
            headers=headers,
            json={
                "name": "Confirmed Detection Alert",
                "severity": "warning",
                "trigger_type": "human_confirmed_detection",
                "cooldown_minutes": 5,
            },
        )
        assert rule_res.status_code == 201, rule_res.text

        # 8. Run real YOLOv8n inference
        job_res = client.post(
            "/api/v1/detections/jobs",
            headers=headers,
            json={
                "media_asset_id": media_id,
                "field_id": field_id,
                "mission_id": mission_id,
                "model_id": "yolov8n-coco-general",
                "confidence_threshold": 0.25,
            },
        )
        assert job_res.status_code == 202, job_res.text
        job_id = job_res.json()["id"]

        mem_before = psutil.Process().memory_info().rss / (1024 * 1024)
        with SessionFactory() as worker_db:
            execute_detection_job_in_session(uuid.UUID(job_id), worker_db, settings)
        job_data = {}
        for _ in range(40):
            detail = client.get(f"/api/v1/detections/jobs/{job_id}")
            assert detail.status_code == 200
            job_data = detail.json()
            if job_data["status"] in {"completed", "failed"}:
                break
            time.sleep(0.25)
        mem_after = psutil.Process().memory_info().rss / (1024 * 1024)

        # 9. View annotated detections
        assert job_data["status"] == "completed"
        assert job_data["model_checksum"]
        assert job_data["inference_ms"] is not None
        assert len(job_data["items"]) >= 1

        ann = client.get(f"/api/v1/detections/jobs/{job_id}/annotated")
        assert ann.status_code == 200
        assert ann.content[:2] == b"\xff\xd8"

        # 10. Review detection (confirmed -> triggers alert + notification)
        first_item_id = job_data["items"][0]["id"]
        rev_res = client.patch(
            f"/api/v1/detections/items/{first_item_id}/review",
            headers=headers,
            json={"review_status": "confirmed", "reviewer_notes": "Phase 7 verified."},
        )
        assert rev_res.status_code == 200, rev_res.text

        # 11. Generate analytics
        ov = client.get("/api/v1/analytics/overview")
        assert ov.status_code == 200
        assert ov.json()["jobs_summary"]["completed_jobs"] == 1
        assert ov.json()["detections_summary"]["human_confirmed_count"] == 1

        # 13. View notifications
        notifs = client.get("/api/v1/notifications")
        assert notifs.status_code == 200
        assert notifs.json()["total"] >= 1

        # 14. Generate and download PDF, CSV, JSON reports
        for fmt in ("pdf", "csv", "json"):
            rep = client.get(f"/api/v1/reports/export?report_type=ai_detection&format={fmt}")
            assert rep.status_code == 200
            assert len(rep.content) > 0

        # Concurrent API request benchmark
        def _hit_health() -> int:
            return client.get("/api/v1/health").status_code

        t_conc0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: _hit_health(), range(16)))
        conc_ms = round((time.perf_counter() - t_conc0) * 1000, 2)
        assert all(s == 200 for s in statuses)

        # 15. Logout
        out = client.post("/api/v1/auth/logout", headers=headers)
        assert out.status_code in (200, 204)

        print(
            f"\n[PHASE7_BENCHMARK] upload_ms={upload_ms} inference_ms={job_data['inference_ms']} "
            f"rss_before_mb={mem_before:.1f} rss_after_mb={mem_after:.1f} concurrent_16_health_ms={conc_ms}"
        )

    # Simulate full application restart: dispose engine, build fresh app & engine on same DB
    engine.dispose()
    app2 = create_app(settings)
    engine2 = build_engine(settings)
    SessionFactory2 = sessionmaker(bind=engine2, autoflush=False, autocommit=False, expire_on_commit=False)

    def _override_db2():
        s = SessionFactory2()
        try:
            yield s
        finally:
            s.close()

    app2.dependency_overrides[get_db_session] = _override_db2
    app2.dependency_overrides[orig_get_settings] = lambda: settings

    with TestClient(app2) as client2:
        login2 = client2.post(
            "/api/v1/auth/login",
            json={"email": "phase7_e2e@agrodrone.io", "password": "StrongPassword!123"},
        )
        assert login2.status_code == 200
        assert client2.get("/api/v1/fields").json()["total"] == 1
        assert client2.get("/api/v1/missions").json()["total"] == 1
        assert client2.get("/api/v1/detections/jobs").json()["total"] == 1
        assert client2.get("/api/v1/alerts").json()["total"] >= 1
    engine2.dispose()
