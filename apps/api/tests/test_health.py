"""Integration tests for health check and request correlation middleware."""

from fastapi.testclient import TestClient


def test_health_check_reports_ok_and_latency(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "AgroDrone API"
    assert body["environment"] == "test"
    assert body["database_connected"] is True
    assert body["database_dialect"] == "sqlite"
    assert isinstance(body["database_latency_ms"], float)
    assert body["database_latency_ms"] >= 0.0


def test_request_id_header_is_preserved(client: TestClient) -> None:
    custom_id = "req-agrodrone-test-001"
    response = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id
