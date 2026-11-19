"""Authentication, user management, and audit log schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import validate_password_policy

UserRole = Literal["admin", "agronomist", "operator", "viewer"]
SelfRegisterRole = Literal["agronomist", "operator", "viewer"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: SelfRegisterRole = "operator"

    @field_validator("full_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned

    @field_validator("password")
    @classmethod
    def check_password_policy(cls, value: str) -> str:
        validate_password_policy(value)
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    logout_all: bool = False


class AuthSessionResponse(BaseModel):
    user: UserRead
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    csrf_token: str


class UserRoleUpdateRequest(BaseModel):
    role: UserRole
    is_active: bool | None = None


class AuthPolicyResponse(BaseModel):
    status: str
    password_hashing: str
    token_scheme: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    csrf_protection: str
    rate_limiting: str
    supported_roles: list[str]
    bootstrap_required: bool
    target_phase: str


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    ip_address: str | None = None
    request_id: str | None = None
    metadata_json: dict[str, Any]
    created_at: datetime
