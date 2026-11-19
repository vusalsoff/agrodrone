"""Contract test ensuring OpenAPI schema covers all Phase 1, Phase 2, and Phase 3 v1 endpoints."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "packages" / "contracts" / "openapi.json"

REQUIRED_PATHS = {
    "/api/v1/health",
    "/api/v1/system/status",
    "/api/v1/system/capabilities",
    "/api/v1/auth/policy",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/users",
    "/api/v1/auth/users/{user_id}/role",
    "/api/v1/auth/audit-logs",
    "/api/v1/fields",
    "/api/v1/fields/{field_id}",
    "/api/v1/devices",
    "/api/v1/devices/{device_id}",
    "/api/v1/missions",
    "/api/v1/missions/{mission_id}",
    "/api/v1/missions/{mission_id}/transition",
    "/api/v1/missions/{mission_id}/observations",
    "/api/v1/media",
    "/api/v1/media/upload",
    "/api/v1/media/presign",
    "/api/v1/media/{media_id}",
    "/api/v1/media/{media_id}/content",
    "/api/v1/media/{media_id}/download-url",
    "/api/v1/detections",
    "/api/v1/detections/models",
    "/api/v1/detections/datasets",
    "/api/v1/detections/jobs",
    "/api/v1/detections/jobs/{job_id}",
    "/api/v1/detections/jobs/{job_id}/cancel",
    "/api/v1/detections/jobs/{job_id}/retry",
    "/api/v1/detections/jobs/{job_id}/annotated",
    "/api/v1/detections/jobs/{job_id}/frames/{frame_index}/annotated",
    "/api/v1/detections/jobs/{job_id}/export",
    "/api/v1/detections/items/{item_id}/review",
    "/api/v1/gateway",
    "/api/v1/gateway/enroll",
    "/api/v1/gateway/{gateway_id}/rotate",
    "/api/v1/gateway/{gateway_id}/revoke",
    "/api/v1/gateway/{gateway_id}/diagnostics",
    "/api/v1/gateway/{gateway_id}/stream/start",
    "/api/v1/gateway/{gateway_id}/stream/stop",
    "/api/v1/gateway/{gateway_id}/stream/latest",
    "/api/v1/gateway/{gateway_id}/snapshots",
    "/api/v1/gateway/snapshots/{media_id}/analyze",
    "/api/v1/gateway/heartbeat",
    "/api/v1/gateway/stream/frame",
    "/api/v1/alerts",
}


def test_live_openapi_and_exported_contract_match(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    live_schema = response.json()

    live_paths = set(live_schema["paths"].keys())
    assert REQUIRED_PATHS.issubset(live_paths)

    assert CONTRACT_PATH.exists(), "packages/contracts/openapi.json must be exported"
    exported_schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert set(exported_schema["paths"].keys()) == live_paths
