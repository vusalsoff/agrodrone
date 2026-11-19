"""Tests for Device CRUD, ESP32-CAM isolated-AP guards, Mission CRUD, state transitions, and observations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient


def test_device_crud_rejects_fabricated_online_status_and_enforces_ownership(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    _admin = register_user("admin@agrodrone.dev")
    agro = register_user("agro@agrodrone.dev", role="agronomist")
    other = register_user("other@agrodrone.dev", role="operator")
    viewer = register_user("viewer@agrodrone.dev", role="viewer")

    field_res = client.post(
        "/api/v1/fields",
        headers=agro["headers"],
        json={"name": "East Wheat Plot", "code": "EW-01"},
    )
    assert field_res.status_code == 201
    field_id = field_res.json()["id"]

    # Viewer cannot register devices
    assert (
        client.post(
            "/api/v1/devices",
            headers=viewer["headers"],
            json={
                "name": "Viewer Device",
                "device_type": "camera_module",
                "device_identifier": "VIEW-01",
                "hardware_model": "ESP32-CAM",
            },
        ).status_code
        == 403
    )

    # Attempting to fabricate "online" status via API is rejected with 422
    fake_online = client.post(
        "/api/v1/devices",
        headers=agro["headers"],
        json={
            "name": "Fake Online ESP32",
            "device_type": "camera_module",
            "device_identifier": "ESP32-FAKE-01",
            "hardware_model": "AI Thinker ESP32-CAM (OV2640)",
            "status": "online",
        },
    )
    assert fake_online.status_code == 422

    # Valid ESP32-CAM registration with isolated AP config
    created = client.post(
        "/api/v1/devices",
        headers=agro["headers"],
        json={
            "name": "Field ESP32-CAM Unit #1",
            "device_type": "camera_module",
            "device_identifier": "ESP32-CAM-001",
            "hardware_model": "AI Thinker ESP32-CAM (OV2640)",
            "assigned_field_id": field_id,
            "connectivity_mode": "isolated_ap",
            "status": "offline_isolated_ap",
            "local_ssid": "agroDrone",
            "local_endpoint_url": "http://192.168.4.1",
            "connection_config": {
                "local_ssid": "agroDrone",
                "local_dashboard_url": "http://192.168.4.1",
                "local_stream_url": "http://192.168.4.1:81/stream",
            },
            "capabilities": {"local_mjpeg": True, "gps": False, "mavlink": False},
        },
    )
    assert created.status_code == 201
    device = created.json()
    assert device["status"] == "offline_isolated_ap"
    assert device["last_authenticated_contact_at"] is None
    assert device["assigned_field_id"] == field_id

    # Cross-user cannot assign agro's field or access agro's device
    cross_assign = client.post(
        "/api/v1/devices",
        headers=other["headers"],
        json={
            "name": "Other Unit",
            "device_type": "camera_module",
            "device_identifier": "ESP32-OTHER-01",
            "hardware_model": "ESP32-CAM",
            "assigned_field_id": field_id,
        },
    )
    assert cross_assign.status_code == 403
    assert client.get(f"/api/v1/devices/{device['id']}", headers=other["headers"]).status_code == 403

    # Update & delete
    updated = client.patch(
        f"/api/v1/devices/{device['id']}",
        headers=agro["headers"],
        json={"status": "maintenance", "unassign_field": True},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "maintenance"
    assert updated.json()["assigned_field_id"] is None

    assert client.delete(f"/api/v1/devices/{device['id']}", headers=agro["headers"]).status_code == 204


def test_mission_lifecycle_state_transitions_and_observations(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    _admin = register_user("admin@agrodrone.dev")
    agro = register_user("agro@agrodrone.dev", full_name="Lead Agronomist", role="agronomist")
    other = register_user("other@agrodrone.dev", full_name="Other Op", role="operator")

    field = client.post(
        "/api/v1/fields",
        headers=agro["headers"],
        json={"name": "South Orchard", "code": "SO-01"},
    ).json()

    device = client.post(
        "/api/v1/devices",
        headers=agro["headers"],
        json={
            "name": "E88 + ESP32 Rig",
            "device_type": "airframe",
            "device_identifier": "E88-RIG-01",
            "hardware_model": "E88 Dual-Camera + ESP32-CAM OV2640",
            "connectivity_mode": "isolated_ap",
        },
    ).json()

    created = client.post(
        "/api/v1/missions",
        headers=agro["headers"],
        json={
            "title": "Morning Canopy Visual Sweep",
            "description": "Manual flight along south rows",
            "field_id": field["id"],
            "device_id": device["id"],
            "status": "draft",
            "operator_notes": "Clear sky, light wind",
        },
    )
    assert created.status_code == 201
    mission_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    # Cross-user access blocked
    assert client.get(f"/api/v1/missions/{mission_id}", headers=other["headers"]).status_code == 403

    # Invalid direct transition draft -> completed rejected with 409
    invalid = client.post(
        f"/api/v1/missions/{mission_id}/transition",
        headers=agro["headers"],
        json={"target_status": "completed"},
    )
    assert invalid.status_code == 409

    # Valid chain: draft -> planned -> in_progress -> completed
    planned = client.post(
        f"/api/v1/missions/{mission_id}/transition",
        headers=agro["headers"],
        json={"target_status": "planned", "note": "Preflight checklist complete"},
    )
    assert planned.status_code == 200
    assert planned.json()["status"] == "planned"
    assert len(planned.json()["observations"]) == 1

    in_prog = client.post(
        f"/api/v1/missions/{mission_id}/transition",
        headers=agro["headers"],
        json={"target_status": "in_progress"},
    )
    assert in_prog.status_code == 200
    assert in_prog.json()["started_at"] is not None

    # Add manual operator observation
    obs = client.post(
        f"/api/v1/missions/{mission_id}/observations",
        headers=agro["headers"],
        json={"note": "Captured 14 OV2640 stills over rows 3-6"},
    )
    assert obs.status_code == 201
    assert len(obs.json()["observations"]) == 2
    assert obs.json()["observations"][-1]["author_name"] == "Lead Agronomist"

    done = client.post(
        f"/api/v1/missions/{mission_id}/transition",
        headers=agro["headers"],
        json={"target_status": "completed"},
    )
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None

    # Terminal state completed cannot transition back
    regress = client.post(
        f"/api/v1/missions/{mission_id}/transition",
        headers=agro["headers"],
        json={"target_status": "in_progress"},
    )
    assert regress.status_code == 409
