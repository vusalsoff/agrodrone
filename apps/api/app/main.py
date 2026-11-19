"""AgroDrone FastAPI application entry point and factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the AgroDrone FastAPI application."""
    cfg = settings or get_settings()
    configure_logging(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        cfg.ensure_local_directories()
        recovery: dict[str, int] = {}
        resumed = 0
        if cfg.environment != "test" and cfg.ai_worker_mode == "inline_thread":
            # Durable local-dev strategy: jobs live in the DB, so a restart requeues orphans and resumes them.
            from sqlalchemy.orm import sessionmaker

            from app.db.session import build_engine
            from app.services.vision import (
                recover_interrupted_jobs,
                resume_queued_jobs_in_thread_pool,
                warmup_available_models,
            )

            factory = sessionmaker(
                bind=build_engine(cfg), autoflush=False, autocommit=False, expire_on_commit=False
            )
            try:
                recovery = recover_interrupted_jobs(factory, cfg)
                resumed = resume_queued_jobs_in_thread_pool(factory, cfg)
            except Exception as exc:  # noqa: BLE001 - never block startup (e.g. before migrations)
                logger.warning("detection_job_recovery_skipped", error=str(exc))
            warmup_available_models(cfg)
        logger.info(
            "api_startup",
            service=cfg.app_name,
            version=cfg.app_version,
            environment=cfg.environment,
            database_dialect=cfg.database_dialect,
            storage_backend=cfg.storage_backend,
            ai_inference_enabled=cfg.ai_inference_enabled,
            ai_worker_mode=cfg.ai_worker_mode,
            ai_device=cfg.ai_device,
            recovered_jobs=recovery,
            resumed_jobs=resumed,
            edge_gateway_enabled=cfg.edge_gateway_enabled,
        )
        yield
        logger.info("api_shutdown", service=cfg.app_name)

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Production-oriented control plane for the AgroDrone AI-Powered Agricultural "
            "Intelligence Platform (Phase 2: Auth, RBAC, Fields/GeoJSON, Devices, Missions & Media)."
        ),
        openapi_url=f"{cfg.api_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "Content-Disposition", "Retry-After"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=cfg.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": cfg.app_name,
            "version": cfg.app_version,
            "docs": "/docs",
            "health": f"{cfg.api_prefix}/health",
        }

    return app


app = create_app()
