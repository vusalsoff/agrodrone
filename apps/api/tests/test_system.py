"""Tests for system status, honest hardware boundaries, and AI capability notices."""

from fastapi.testclient import TestClient


def test_system_status_reports_real_zero_counts_and_subsystems(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200

    body = response.json()
    assert body["database_connected"] is True
    assert body["ai_inference_enabled"] is False
    assert body["edge_gateway_enabled"] is False
    assert body["counts"] == {
        "fields": 0,
        "devices": 0,
        "missions": 0,
        "media_assets": 0,
        "detection_jobs": 0,
        "open_alerts": 0,
    }

    subsystem_ids = {item["id"] for item in body["subsystems"]}
    assert {"api", "database", "storage", "ai_worker", "edge_gateway"} == subsystem_ids


def test_capabilities_enforce_hardware_and_ai_honesty(client: TestClient) -> None:
    response = client.get("/api/v1/system/capabilities")
    assert response.status_code == 200

    body = response.json()

    boundary = body["network_boundary"]
    assert boundary["esp32_ap_ssid"] == "agroDrone"
    assert boundary["esp32_dashboard_url"] == "http://192.168.4.1"
    assert boundary["esp32_mjpeg_stream_url"] == "http://192.168.4.1:81/stream"
    assert boundary["direct_cloud_probe_allowed"] is False

    assert len(body["hardware_baseline"]) == 4
    for hw in body["hardware_baseline"]:
        assert hw["cloud_directly_reachable"] is False

    ai_policy = body["ai_policy"]
    assert ai_policy["inference_enabled"] is False
    assert "snakes" in ai_policy["model_honesty_notice"].lower()
    assert "hedgehogs" in ai_policy["model_honesty_notice"].lower()
    assert "insects" in ai_policy["model_honesty_notice"].lower()
    assert "crop diseases" in ai_policy["model_honesty_notice"].lower()

    assert len(body["modules"]) == 12
