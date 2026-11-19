"""Double-submit CSRF protection for cookie-authenticated state-changing requests."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import AuthorizationError
from app.core.security import constant_time_equals

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def verify_csrf_if_cookie_auth(request: Request, settings: Settings) -> None:
    """Require matching X-CSRF-Token header when authenticating via session cookies.

    Pure Bearer-header clients (without auth cookies) are exempt from cookie-based CSRF.
    """
    if request.method.upper() not in MUTATING_METHODS:
        return

    auth_header = request.headers.get("Authorization", "")
    has_bearer = auth_header.lower().startswith("bearer ") and len(auth_header) > 7
    has_auth_cookie = bool(
        request.cookies.get(settings.access_cookie_name)
        or request.cookies.get(settings.refresh_cookie_name)
    )

    if has_bearer and not has_auth_cookie:
        return

    if not has_auth_cookie:
        return

    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get(settings.csrf_header_name)
    if not constant_time_equals(csrf_cookie, csrf_header):
        raise AuthorizationError("CSRF token validation failed.")
