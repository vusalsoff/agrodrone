"""SQLAlchemy engine and session factory helpers with production PostgreSQL pooling."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    """Build a SQLAlchemy 2.0 engine configured for PostgreSQL pooling or local SQLite."""
    settings.ensure_local_directories()

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, Any] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }

    if settings.database_dialect == "sqlite":
        connect_args["check_same_thread"] = False
    else:
        engine_kwargs["pool_size"] = settings.db_pool_size
        engine_kwargs["max_overflow"] = settings.db_max_overflow
        engine_kwargs["pool_timeout"] = settings.db_pool_timeout
        engine_kwargs["pool_recycle"] = settings.db_pool_recycle

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )

    if settings.database_dialect == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_default_settings = get_settings()
engine = build_engine(_default_settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a managed SQLAlchemy session per HTTP request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
