"""Phase 6 tests: Production config hardening, readiness/metrics probes, security headers & worker healthcheck."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.worker import HEARTBEAT_FILE, _run_healthcheck, _write_heartbeat


def test_production_settings_reject_insecure_defaults() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            environment="production",
            jwt_secret_key="local-dev-only-secret-change-before-production-32chars",
            cors_origins=["https://app.agrodrone.io"],
            storage_backend="local",
        )

    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            jwt_secret_key="x" * 48,
            cors_origins=["*"],
            storage_backend="local",
        )

    with pytest.raises(ValidationError, match="ALLOW_DIRECT_LOCAL_CAMERA_PROBE"):
        Settings(
            environment="production",
            jwt_secret_key="x" * 48,
            cors_origins=["https://app.agrodrone.io"],
            allow_direct_local_camera_probe=True,
            storage_backend="local",
        )

    with pytest.raises(ValidationError, match="S3_ACCESS_KEY_ID"):
        Settings(
            environment="production",
            jwt_secret_key="x" * 48,
            cors_origins=["https://app.agrodrone.io"],
            storage_backend="s3",
            s3_access_key_id="",
            s3_secret_access_key="",
        )

    valid_prod = Settings(
        environment="production",
        jwt_secret_key="prod-random-secret-key-with-sufficient-entropy-123456",
        cors_origins=["https://app.agrodrone.io"],
        storage_backend="s3",
        s3_use_iam_role=True,
        local_no_auth_mode=False,
    )
    assert valid_prod.environment == "production"


def test_readiness_metrics_and_security_headers(client: TestClient) -> None:
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["ready"] is True
    assert body["database_ready"] is True
    assert body["storage_ready"] is True

    # Security headers enforced on API responses
    assert ready.headers["X-Content-Type-Options"] == "nosniff"
    assert ready.headers["X-Frame-Options"] == "DENY"
    assert ready.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "X-Request-ID" in ready.headers

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    m = metrics.json()
    assert "queued_detection_jobs" in m
    assert "open_alerts" in m
    assert "active_edge_gateways" in m


def test_worker_healthcheck_succeeds_with_local_db() -> None:
    _write_heartbeat()
    assert _run_healthcheck() == 0
    HEARTBEAT_FILE.write_text(str(time.time() - 3600), encoding="utf-8")
    assert _run_healthcheck() == 1
    _write_heartbeat()
