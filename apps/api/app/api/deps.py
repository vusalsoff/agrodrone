"""FastAPI dependency providers: DB session, settings, cookie/Bearer auth, CSRF, and RBAC."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.csrf import verify_csrf_if_cookie_auth
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def _extract_access_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> str:
    if credentials is not None and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(settings.access_cookie_name)
    if cookie_token:
        return cookie_token
    raise AuthenticationError("Authentication required. Please sign in.")


def _get_or_create_local_operator(db: Session) -> User:
    from sqlalchemy import select

    from app.core.security import hash_password

    existing = db.scalar(select(User).order_by(User.created_at.asc()))
    if existing is not None:
        return existing
    user = User(
        email="operator@agrodrone.io",
        full_name="AgroDrone Operator",
        hashed_password=hash_password("LocalOperator!12345"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    """Resolve authenticated active User from Bearer token or HttpOnly cookie + CSRF check."""
    has_cookie = bool(request.cookies.get(settings.access_cookie_name))
    has_bearer = credentials is not None and bool(credentials.credentials)
    if (
        not has_cookie
        and not has_bearer
        and settings.local_no_auth_mode
        and settings.environment == "development"
    ):
        return _get_or_create_local_operator(db)

    verify_csrf_if_cookie_auth(request, settings)
    raw_token = _extract_access_token(request, credentials, settings)
    claims = decode_access_token(raw_token, settings)

    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed subject claim in access token.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")

    return user


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    """Build a FastAPI dependency enforcing role membership on the backend."""

    def _dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise AuthorizationError(
                f"Role '{user.role}' is not permitted for this operation."
            )
        return user

    return _dependency


def enforce_owner_or_admin(owner_id: uuid.UUID | None, current_user: User) -> None:
    """Block cross-user access unless the authenticated actor is an Admin."""
    if current_user.role == "admin":
        return
    if owner_id is None or owner_id != current_user.id:
        raise AuthorizationError("You do not have permission to access this resource.")


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DBSessionDep = Annotated[Session, Depends(get_db_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminUserDep = Annotated[User, Depends(require_roles("admin"))]
FieldWriterDep = Annotated[User, Depends(require_roles("admin", "agronomist"))]
OperatorWriterDep = Annotated[User, Depends(require_roles("admin", "agronomist", "operator"))]
