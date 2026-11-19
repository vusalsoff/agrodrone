"""Tests for Field CRUD, geodesic GeoJSON polygon validation, RBAC, and cross-user isolation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.geo import validate_and_measure_polygon

# Roughly 1 km x 1 km parcel at ~40.4 deg N (~100 hectares; actual WGS-84 ~93-95 ha)
VALID_PARCEL_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [
            [49.8500, 40.4000],
            [49.8618, 40.4000],
            [49.8618, 40.4090],
            [49.8500, 40.4090],
            [49.8500, 40.4000],
        ]
    ],
}

SMALLER_PARCEL_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [
            [49.8500, 40.4000],
            [49.8559, 40.4000],
            [49.8559, 40.4045],
            [49.8500, 40.4045],
            [49.8500, 40.4000],
        ]
    ],
}


def test_geodesic_area_calculation_accuracy() -> None:
    metrics = validate_and_measure_polygon(VALID_PARCEL_POLYGON)
    # 0.0118 deg lng * cos(40.4 deg) * 111.32 km ~= 1.00 km; 0.009 deg lat * 111.32 km ~= 1.00 km => ~100 ha
    assert 98.0 <= metrics.area_hectares <= 103.0
    assert 40.404 <= metrics.centroid_lat <= 40.405
    assert 49.855 <= metrics.centroid_lng <= 49.857


@pytest.mark.parametrize(
    "bad_geojson",
    [
        # Unclosed ring
        {"type": "Polygon", "coordinates": [[[49.8, 40.4], [49.9, 40.4], [49.9, 40.5], [49.8, 40.5]]]},
        # Too few points
        {"type": "Polygon", "coordinates": [[[49.8, 40.4], [49.9, 40.4], [49.8, 40.4]]]},
        # Out-of-range longitude
        {
            "type": "Polygon",
            "coordinates": [[[200.0, 40.4], [201.0, 40.4], [201.0, 40.5], [200.0, 40.4]]],
        },
        # Self-intersecting bowtie polygon
        {
            "type": "Polygon",
            "coordinates": [
                [[49.8, 40.4], [49.9, 40.5], [49.9, 40.4], [49.8, 40.5], [49.8, 40.4]]
            ],
        },
        # Wrong GeoJSON geometry type
        {"type": "Point", "coordinates": [49.8, 40.4]},
    ],
)
def test_invalid_field_polygons_are_rejected(
    client: TestClient,
    register_user: Callable[..., dict[str, Any]],
    bad_geojson: dict[str, Any],
) -> None:
    admin = register_user("geo-admin@agrodrone.dev")
    res = client.post(
        "/api/v1/fields",
        headers=admin["headers"],
        json={
            "name": "Invalid Parcel",
            "code": "BAD-01",
            "boundary_geojson": bad_geojson,
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_INPUT"


def test_field_crud_polygon_edit_search_and_cross_user_isolation(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    admin = register_user("admin@agrodrone.dev", full_name="Admin")
    agro_a = register_user("agro-a@agrodrone.dev", full_name="Agronomist A", role="agronomist")
    agro_b = register_user("agro-b@agrodrone.dev", full_name="Agronomist B", role="agronomist")
    operator = register_user("op@agrodrone.dev", full_name="Operator", role="operator")
    viewer = register_user("viewer@agrodrone.dev", full_name="Viewer", role="viewer")

    # Viewer and Operator cannot create fields
    for actor in (operator, viewer):
        denied = client.post(
            "/api/v1/fields",
            headers=actor["headers"],
            json={"name": "Forbidden Field", "code": "NO-01"},
        )
        assert denied.status_code == 403

    # Agronomist A creates a field with GeoJSON boundary
    created = client.post(
        "/api/v1/fields",
        headers=agro_a["headers"],
        json={
            "name": "North Vineyard Block A",
            "code": "nv-a01",
            "location": "Ganja Foothills",
            "crop_type": "Grapes",
            "description": "Irrigated hillside rows",
            "boundary_geojson": VALID_PARCEL_POLYGON,
        },
    )
    assert created.status_code == 201
    field_a = created.json()
    assert field_a["code"] == "NV-A01"
    assert field_a["owner_id"] == agro_a["user"]["id"]
    assert 98.0 <= field_a["area_hectares"] <= 103.0
    assert field_a["centroid_lat"] is not None

    # Duplicate code fails with 409
    dup = client.post(
        "/api/v1/fields",
        headers=agro_a["headers"],
        json={"name": "Duplicate", "code": "NV-A01"},
    )
    assert dup.status_code == 409

    # Cross-user isolation: Agronomist B sees 0 fields and gets 403 on direct read/patch/delete
    assert client.get("/api/v1/fields", headers=agro_b["headers"]).json()["total"] == 0
    assert client.get(f"/api/v1/fields/{field_a['id']}", headers=agro_b["headers"]).status_code == 403
    assert (
        client.patch(
            f"/api/v1/fields/{field_a['id']}",
            headers=agro_b["headers"],
            json={"name": "Hijack"},
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/fields/{field_a['id']}", headers=agro_b["headers"]).status_code == 403

    # Admin can see Agronomist A's field
    assert client.get("/api/v1/fields", headers=admin["headers"]).json()["total"] == 1

    # Search & filter
    search_hit = client.get(
        "/api/v1/fields?q=Vineyard&crop_type=Grapes&has_boundary=true",
        headers=agro_a["headers"],
    )
    assert search_hit.status_code == 200
    assert search_hit.json()["total"] == 1

    # Edit polygon recalculates area (~25 ha)
    edited = client.patch(
        f"/api/v1/fields/{field_a['id']}",
        headers=agro_a["headers"],
        json={"boundary_geojson": SMALLER_PARCEL_POLYGON},
    )
    assert edited.status_code == 200
    assert 24.0 <= edited.json()["area_hectares"] <= 26.5

    # Delete polygon cleanly clears geometry & centroid
    cleared = client.patch(
        f"/api/v1/fields/{field_a['id']}",
        headers=agro_a["headers"],
        json={"clear_boundary": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["boundary_geojson"] is None
    assert cleared.json()["centroid_lat"] is None

    # Delete field
    deleted = client.delete(f"/api/v1/fields/{field_a['id']}", headers=agro_a["headers"])
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/fields/{field_a['id']}", headers=agro_a["headers"]).status_code == 404
