"""Integration tests for protected resource lists and standard error envelopes."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient


def test_protected_resources_reject_unauthenticated_requests(client: TestClient) -> None:
    for path in (
        "/api/v1/fields",
        "/api/v1/devices",
        "/api/v1/missions",
        "/api/v1/media",
        "/api/v1/detections",
        "/api/v1/detections/models",
        "/api/v1/detections/jobs",
        "/api/v1/alerts",
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_paginated_empty_resource_lists_when_authenticated(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    admin = register_user("admin@agrodrone.dev")
    for path in (
        "/api/v1/fields",
        "/api/v1/devices",
        "/api/v1/missions",
        "/api/v1/media",
        "/api/v1/detections",
        "/api/v1/detections/jobs",
        "/api/v1/detections/datasets",
        "/api/v1/alerts",
    ):
        response = client.get(path, headers=admin["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0


def test_validation_error_uses_standard_envelope(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    admin = register_user("admin@agrodrone.dev")
    response = client.get("/api/v1/fields?limit=9999", headers=admin["headers"])
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
