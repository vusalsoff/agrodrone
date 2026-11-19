"""Authentication, session management (cookies + refresh rotation + CSRF), RBAC users, and audit logs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep, SettingsDep
from app.core.audit import record_audit_event
from app.core.config import Settings
from app.core.csrf import verify_csrf_if_cookie_auth
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)
from app.core.rate_limit import enforce_auth_rate_limit, extract_client_ip
from app.core.security import (
    create_access_token,
    dummy_verify_password,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    AuditLogRead,
    AuthPolicyResponse,
    AuthSessionResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    UserRead,
    UserRoleUpdateRequest,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(
    *,
    response: Response,
    settings: Settings,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    access_max_age = settings.jwt_access_token_expire_minutes * 60
    refresh_max_age = settings.jwt_refresh_token_expire_days * 24 * 60 * 60

    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
        max_age=access_max_age,
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=f"{settings.api_prefix}/auth",
        max_age=refresh_max_age,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.use_secure_cookies,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
        max_age=refresh_max_age,
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.access_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_prefix}/auth",
        domain=settings.cookie_domain,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )


def _issue_session(
    *,
    db: DBSessionDep,
    user: User,
    request: Request,
    response: Response,
    settings: Settings,
    token_family: uuid.UUID | None = None,
) -> tuple[AuthSessionResponse, RefreshToken]:
    now = datetime.now(UTC)
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        settings=settings,
    )
    raw_refresh = generate_opaque_token(48)
    csrf_token = generate_opaque_token(32)

    refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_opaque_token(raw_refresh),
        token_family=token_family or uuid.uuid4(),
        expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
        ip_address=extract_client_ip(request),
        user_agent=(request.headers.get("User-Agent") or "")[:255] or None,
    )
    db.add(refresh_row)
    db.flush()

    _set_session_cookies(
        response=response,
        settings=settings,
        access_token=access_token,
        refresh_token=raw_refresh,
        csrf_token=csrf_token,
    )

    session = AuthSessionResponse(
        user=UserRead.model_validate(user),
        access_token=access_token,
        expires_in_seconds=settings.jwt_access_token_expire_minutes * 60,
        csrf_token=csrf_token,
    )
    return session, refresh_row


@router.get(
    "/policy",
    response_model=AuthPolicyResponse,
    summary="Inspect active security, CSRF, rate-limit, and bootstrap policy",
)
def get_auth_policy(db: DBSessionDep, settings: SettingsDep) -> AuthPolicyResponse:
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    return AuthPolicyResponse(
        status="phase2_active",
        password_hashing="Argon2id (argon2-cffi)",
        token_scheme=f"JWT ({settings.jwt_algorithm}) + HttpOnly rotating refresh tokens",
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
        csrf_protection=f"Double-submit cookie ({settings.csrf_cookie_name} + {settings.csrf_header_name})",
        rate_limiting=f"{settings.auth_rate_limit_requests} requests / {settings.auth_rate_limit_window_seconds}s per IP",
        supported_roles=["admin", "agronomist", "operator", "viewer"],
        bootstrap_required=user_count == 0,
        target_phase="Phase 2 (Active)",
    )


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new AgroDrone account (first account bootstraps Admin)",
)
def register_user(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: DBSessionDep,
    settings: SettingsDep,
) -> AuthSessionResponse:
    enforce_auth_rate_limit(request, settings, scope="auth_register")
    normalized_email = payload.email.strip().lower()

    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise ConflictError("An account with this email address already exists.")

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    assigned_role = "admin" if total_users == 0 else payload.role

    user = User(
        email=normalized_email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=assigned_role,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An account with this email address already exists.") from exc

    session, _ = _issue_session(
        db=db,
        user=user,
        request=request,
        response=response,
        settings=settings,
    )
    record_audit_event(
        db,
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        actor=user,
        request=request,
        metadata={"assigned_role": assigned_role, "bootstrap_admin": total_users == 0},
    )
    db.commit()
    return session


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="Authenticate with email and password",
)
def login_user(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSessionDep,
    settings: SettingsDep,
) -> AuthSessionResponse:
    enforce_auth_rate_limit(request, settings, scope="auth_login")
    normalized_email = payload.email.strip().lower()

    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        dummy_verify_password(payload.password)
        record_audit_event(
            db,
            action="auth.login_failed",
            resource_type="user",
            actor_email=normalized_email,
            request=request,
            metadata={"reason": "invalid_credentials"},
        )
        db.commit()
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active or not verify_password(payload.password, user.password_hash):
        record_audit_event(
            db,
            action="auth.login_failed",
            resource_type="user",
            resource_id=user.id,
            actor_email=normalized_email,
            request=request,
            metadata={"reason": "inactive_or_invalid_password"},
        )
        db.commit()
        raise AuthenticationError("Invalid email or password.")

    session, _ = _issue_session(
        db=db,
        user=user,
        request=request,
        response=response,
        settings=settings,
    )
    record_audit_event(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        actor=user,
        request=request,
    )
    db.commit()
    return session


@router.post(
    "/refresh",
    response_model=AuthSessionResponse,
    summary="Rotate refresh token and issue a fresh access token",
)
def refresh_session(
    request: Request,
    response: Response,
    db: DBSessionDep,
    settings: SettingsDep,
    payload: RefreshRequest | None = None,
) -> AuthSessionResponse:
    enforce_auth_rate_limit(request, settings, scope="auth_refresh")

    cookie_refresh = request.cookies.get(settings.refresh_cookie_name)
    if cookie_refresh:
        verify_csrf_if_cookie_auth(request, settings)
        raw_refresh = cookie_refresh
    elif payload and payload.refresh_token:
        raw_refresh = payload.refresh_token
    else:
        raise AuthenticationError("Refresh token is missing.")

    token_hash = hash_opaque_token(raw_refresh)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored is None:
        _clear_session_cookies(response, settings)
        raise AuthenticationError("Refresh token is invalid.")

    now = datetime.now(UTC)

    # Reuse detection: presenting an already revoked/rotated refresh token invalidates the entire family.
    if stored.revoked_at is not None:
        family_tokens = db.scalars(
            select(RefreshToken).where(
                RefreshToken.token_family == stored.token_family,
                RefreshToken.revoked_at.is_(None),
            )
        ).all()
        for tok in family_tokens:
            tok.revoked_at = now
        record_audit_event(
            db,
            action="auth.refresh_reuse_detected",
            resource_type="refresh_token",
            resource_id=stored.id,
            request=request,
            metadata={"token_family": str(stored.token_family), "user_id": str(stored.user_id)},
        )
        db.commit()
        _clear_session_cookies(response, settings)
        raise AuthenticationError("Refresh token reuse detected. All sessions in this family were revoked.")

    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        stored.revoked_at = now
        db.commit()
        _clear_session_cookies(response, settings)
        raise AuthenticationError("Refresh token has expired. Please sign in again.")

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        stored.revoked_at = now
        db.commit()
        _clear_session_cookies(response, settings)
        raise AuthenticationError("Account is inactive or no longer exists.")

    session, new_refresh = _issue_session(
        db=db,
        user=user,
        request=request,
        response=response,
        settings=settings,
        token_family=stored.token_family,
    )
    stored.revoked_at = now
    stored.replaced_by_id = new_refresh.id
    record_audit_event(
        db,
        action="auth.refresh",
        resource_type="user",
        resource_id=user.id,
        actor=user,
        request=request,
    )
    db.commit()
    return session


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token(s) and clear session cookies",
)
def logout_user(
    request: Request,
    response: Response,
    current_user: CurrentUserDep,
    db: DBSessionDep,
    settings: SettingsDep,
    payload: LogoutRequest | None = None,
) -> Response:
    now = datetime.now(UTC)
    logout_all = bool(payload.logout_all) if payload else False

    if logout_all:
        active_tokens = db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
        ).all()
        for tok in active_tokens:
            tok.revoked_at = now
    else:
        raw_refresh = request.cookies.get(settings.refresh_cookie_name)
        if raw_refresh:
            stored = db.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(raw_refresh))
            )
            if stored is not None and stored.user_id == current_user.id:
                stored.revoked_at = now

    record_audit_event(
        db,
        action="auth.logout",
        resource_type="user",
        resource_id=current_user.id,
        actor=current_user,
        request=request,
        metadata={"logout_all": logout_all},
    )
    db.commit()
    _clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead, summary="Return authenticated user profile")
def get_me(current_user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get(
    "/users",
    response_model=PaginatedResponse[UserRead],
    summary="List platform users (Admin only)",
)
def list_users(
    _admin: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[UserRead]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[UserRead](
        items=[UserRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    summary="Update user role or active status (Admin only)",
)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    request: Request,
    admin: AdminUserDep,
    db: DBSessionDep,
) -> UserRead:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User", str(user_id))

    if target.id == admin.id and (payload.role != "admin" or payload.is_active is False):
        raise ValidationAppError("An administrator cannot demote or deactivate their own account.")

    previous_role = target.role
    target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
        if not payload.is_active:
            now = datetime.now(UTC)
            active_tokens = db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == target.id,
                    RefreshToken.revoked_at.is_(None),
                )
            ).all()
            for tok in active_tokens:
                tok.revoked_at = now

    record_audit_event(
        db,
        action="user.role_update",
        resource_type="user",
        resource_id=target.id,
        actor=admin,
        request=request,
        metadata={
            "previous_role": previous_role,
            "new_role": target.role,
            "is_active": target.is_active,
        },
    )
    db.commit()
    db.refresh(target)
    return UserRead.model_validate(target)


@router.get(
    "/audit-logs",
    response_model=PaginatedResponse[AuditLogRead],
    summary="List security and mutation audit logs (Admin only)",
)
def list_audit_logs(
    _admin: AdminUserDep,
    db: DBSessionDep,
    action: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AuditLogRead]:
    base_query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)
    if action:
        base_query = base_query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    total = db.scalar(count_query) or 0
    rows = db.scalars(
        base_query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return PaginatedResponse[AuditLogRead](
        items=[AuditLogRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
