"""Comprehensive tests for registration, cookies, CSRF, refresh rotation, reuse revocation, RBAC, and rate limiting."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings


def test_bootstrap_first_user_is_admin_and_second_respects_role(client: TestClient) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json={
            "email": "founder@agrodrone.dev",
            "full_name": "Founder Admin",
            "password": "StrongPass#2026",
            "role": "viewer",
        },
    )
    assert first.status_code == 201
    assert first.json()["user"]["role"] == "admin"

    client.cookies.clear()
    second = client.post(
        "/api/v1/auth/register",
        json={
            "email": "field@agrodrone.dev",
            "full_name": "Field Agronomist",
            "password": "StrongPass#2026",
            "role": "agronomist",
        },
    )
    assert second.status_code == 201
    assert second.json()["user"]["role"] == "agronomist"

    # Cannot self-register as admin via schema validation
    client.cookies.clear()
    escalate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "hacker@agrodrone.dev",
            "full_name": "Escalation Attempt",
            "password": "StrongPass#2026",
            "role": "admin",
        },
    )
    assert escalate.status_code == 422


def test_cookie_login_csrf_protection_and_refresh_reuse_detection(
    client: TestClient, test_settings: Settings
) -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "csrf@agrodrone.dev",
            "full_name": "CSRF Admin",
            "password": "StrongPass#2026",
        },
    )
    assert reg.status_code == 201

    client.cookies.clear()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "csrf@agrodrone.dev", "password": "StrongPass#2026"},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]
    initial_refresh = client.cookies.get(test_settings.refresh_cookie_name)
    assert initial_refresh is not None
    assert client.cookies.get(test_settings.access_cookie_name) is not None

    # GET works via HttpOnly cookie without CSRF header
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "csrf@agrodrone.dev"

    # Cookie-authenticated mutating POST without CSRF header MUST fail with 403
    blocked = client.post(
        "/api/v1/fields",
        json={"name": "Blocked Field", "code": "BLK-01"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "FORBIDDEN"

    # With matching X-CSRF-Token header it succeeds
    allowed = client.post(
        "/api/v1/fields",
        headers={test_settings.csrf_header_name: csrf_token},
        json={"name": "Allowed Field", "code": "ALW-01"},
    )
    assert allowed.status_code == 201

    # Rotate refresh token using cookie + CSRF
    rotated = client.post(
        "/api/v1/auth/refresh",
        headers={test_settings.csrf_header_name: csrf_token},
    )
    assert rotated.status_code == 200
    rotated_csrf = rotated.json()["csrf_token"]
    new_refresh = client.cookies.get(test_settings.refresh_cookie_name)
    assert new_refresh is not None
    assert new_refresh != initial_refresh

    # Presenting the OLD already-rotated refresh token MUST trigger reuse detection & revoke family
    client.cookies.set(test_settings.refresh_cookie_name, initial_refresh)
    replay = client.post(
        "/api/v1/auth/refresh",
        headers={test_settings.csrf_header_name: rotated_csrf},
    )
    assert replay.status_code == 401
    assert "reuse detected" in replay.json()["error"]["message"].lower()

    # Even the newer token from the compromised family is now revoked!
    client.cookies.set(test_settings.refresh_cookie_name, new_refresh)
    client.cookies.set(test_settings.csrf_cookie_name, rotated_csrf)
    post_compromise = client.post(
        "/api/v1/auth/refresh",
        headers={test_settings.csrf_header_name: rotated_csrf},
    )
    assert post_compromise.status_code == 401


def test_logout_revokes_session_and_clears_cookies(
    client: TestClient, test_settings: Settings
) -> None:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@agrodrone.dev",
            "full_name": "Logout User",
            "password": "StrongPass#2026",
        },
    )
    assert res.status_code == 201
    csrf = res.json()["csrf_token"]
    refresh_val = client.cookies.get(test_settings.refresh_cookie_name)
    assert refresh_val is not None

    out = client.post(
        "/api/v1/auth/logout",
        headers={test_settings.csrf_header_name: csrf},
        json={"logout_all": True},
    )
    assert out.status_code == 204

    # Attempting refresh with revoked token fails
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_val})
    assert replay.status_code == 401


def test_admin_rbac_user_role_management_and_audit_logs(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    admin = register_user("admin@agrodrone.dev", full_name="Primary Admin")
    operator = register_user("op@agrodrone.dev", full_name="Field Op", role="operator")

    # Non-admin blocked from listing users and audit logs
    assert client.get("/api/v1/auth/users", headers=operator["headers"]).status_code == 403
    assert client.get("/api/v1/auth/audit-logs", headers=operator["headers"]).status_code == 403

    # Admin can promote operator to agronomist
    users_res = client.get("/api/v1/auth/users", headers=admin["headers"])
    assert users_res.status_code == 200
    assert users_res.json()["total"] == 2

    update_res = client.patch(
        f"/api/v1/auth/users/{operator['user']['id']}/role",
        headers=admin["headers"],
        json={"role": "agronomist"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["role"] == "agronomist"

    # Admin cannot self-demote
    self_demote = client.patch(
        f"/api/v1/auth/users/{admin['user']['id']}/role",
        headers=admin["headers"],
        json={"role": "viewer"},
    )
    assert self_demote.status_code == 422

    # Audit logs capture register & role_update without secrets
    audit_res = client.get("/api/v1/auth/audit-logs", headers=admin["headers"])
    assert audit_res.status_code == 200
    actions = {entry["action"] for entry in audit_res.json()["items"]}
    assert "auth.register" in actions
    assert "user.role_update" in actions


def test_auth_rate_limiting_triggers_429(client: TestClient, test_settings: Settings) -> None:
    # Override limit tightly for deterministic rate-limit test
    test_settings.auth_rate_limit_requests = 3
    for _ in range(3):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@agrodrone.dev", "password": "WrongPassword1"},
        )
        assert res.status_code == 401

    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@agrodrone.dev", "password": "WrongPassword1"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in limited.headers
