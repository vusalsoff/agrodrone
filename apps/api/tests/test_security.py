"""Unit tests for Argon2id password hashing and JWT access token lifecycle."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    hashed = hash_password("StrongAgroPass#2026")
    assert hashed != "StrongAgroPass#2026"
    assert hashed.startswith("$argon2id$")
    assert verify_password("StrongAgroPass#2026", hashed) is True
    assert verify_password("WrongPassword#2026", hashed) is False


def test_password_min_length_enforced() -> None:
    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("short")


def test_jwt_create_and_decode(test_settings: Settings) -> None:
    token = create_access_token(
        subject="user-123",
        role="agronomist",
        settings=test_settings,
    )
    claims = decode_access_token(token, test_settings)
    assert claims["sub"] == "user-123"
    assert claims["role"] == "agronomist"
    assert claims["type"] == "access"


def test_jwt_expired_token_rejected(test_settings: Settings) -> None:
    expired = create_access_token(
        subject="user-123",
        role="operator",
        settings=test_settings,
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(expired, test_settings)


def test_auth_policy_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/auth/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "phase2_active"
    assert "Argon2id" in body["password_hashing"]
    assert set(body["supported_roles"]) == {"admin", "agronomist", "operator", "viewer"}
    assert body["bootstrap_required"] is True
