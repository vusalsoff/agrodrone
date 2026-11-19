"""Security primitives: Argon2id password hashing, JWT access tokens, and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)

# Pre-computed dummy Argon2id hash used to equalize login latency for unknown emails.
_DUMMY_PASSWORD_HASH = _password_hasher.hash("AgroDrone#DummyTimingGuard2026")

VALID_ROLES = ("admin", "agronomist", "operator", "viewer")


def validate_password_policy(plain_password: str) -> None:
    """Enforce baseline enterprise password strength rules."""
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(plain_password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not any(ch.islower() for ch in plain_password):
        raise ValueError("Password must include at least one lowercase letter.")
    if not any(ch.isupper() for ch in plain_password):
        raise ValueError("Password must include at least one uppercase letter.")
    if not any(ch.isdigit() for ch in plain_password):
        raise ValueError("Password must include at least one digit.")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify_password(plain_password: str) -> None:
    """Run constant-cost verification when email is unknown to resist timing enumeration."""
    verify_password(plain_password, _DUMMY_PASSWORD_HASH)


def generate_opaque_token(num_bytes: int = 48) -> str:
    """Generate a high-entropy URL-safe opaque token (for refresh or CSRF)."""
    return secrets.token_urlsafe(num_bytes)


def hash_opaque_token(token: str) -> str:
    """Compute SHA-256 hex digest of an opaque token for database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str | None, b: str | None) -> bool:
    """Constant-time string comparison for CSRF/secret verification."""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def create_access_token(
    *,
    subject: str,
    role: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a signed JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid or expired.") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.")

    return payload
