"""Standardized domain exceptions and FastAPI error handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base structured application error."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str | None = None) -> None:
        detail = f"{resource} not found" if not identifier else f"{resource} '{identifier}' not found"
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=detail,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationAppError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="INVALID_INPUT",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class PayloadTooLargeError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="PAYLOAD_TOO_LARGE",
            message=message,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            details=details,
        )


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication credentials are invalid or expired.") -> None:
        super().__init__(
            code="AUTHENTICATION_FAILED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class RateLimitError(AppError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many authentication attempts. Please retry later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(retry_after_seconds)},
        )


class FeatureNotEnabledError(AppError):
    def __init__(self, feature: str, target_phase: str, reason: str | None = None) -> None:
        msg = f"{feature} is not active yet (scheduled for {target_phase})."
        if reason:
            msg = f"{msg} {reason}"
        super().__init__(
            code="FEATURE_NOT_ENABLED",
            message=msg,
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            details={"feature": feature, "target_phase": target_phase},
        )


def _error_envelope(
    *,
    code: str,
    message: str,
    request_id: str | None,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach consistent JSON error handlers to the FastAPI application."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "app_error",
            code=exc.code,
            status_code=exc.status_code,
            path=request.url.path,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_error_envelope(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_envelope(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                request_id=request_id,
                details=exc.errors(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            request_id=request_id,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
                request_id=request_id,
            ),
        )
