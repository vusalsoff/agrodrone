"""Pytest fixtures providing isolated migrated databases, rate-limit reset, and auth helpers."""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_app_settings, get_db_session
from app.core.config import Settings
from app.core.rate_limit import auth_rate_limiter
from app.db.session import build_engine
from app.main import create_app
from app.services.gateway_relay import frame_relay_store, gateway_replay_guard

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None, None, None]:
    auth_rate_limiter.reset()
    frame_relay_store.reset_all()
    gateway_replay_guard.reset()
    yield
    auth_rate_limiter.reset()
    frame_relay_store.reset_all()
    gateway_replay_guard.reset()


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    db_file = tmp_path / "test_agrodrone.db"
    storage_dir = tmp_path / "storage"
    return Settings(
        environment="test",
        log_level="WARNING",
        log_format="console",
        database_url=f"sqlite:///{db_file.as_posix()}",
        storage_backend="local",
        local_storage_path=storage_dir.as_posix(),
        jwt_secret_key="pytest-only-secret-key-with-more-than-32-characters",
        auth_rate_limit_requests=50,
        auth_rate_limit_window_seconds=60,
        max_image_upload_bytes=1024 * 1024,
        max_video_upload_bytes=2 * 1024 * 1024,
        allow_direct_local_camera_probe=False,
        ai_inference_enabled=False,
        edge_gateway_enabled=False,
    )


@pytest.fixture()
def db_session(test_settings: Settings) -> Generator[Session, None, None]:
    alembic_cfg = Config(str(API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_settings.database_url)
    command.upgrade(alembic_cfg, "head")

    engine = build_engine(test_settings)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(test_settings: Settings, db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app(test_settings)

    def _override_settings() -> Settings:
        return test_settings

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_app_settings] = _override_settings
    app.dependency_overrides[get_db_session] = _override_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def register_user(client: TestClient) -> Callable[..., dict[str, Any]]:
    """Helper to register a user and return session payload + Authorization Bearer headers."""

    def _register(
        email: str,
        password: str = "StrongPass#2026",
        full_name: str = "Test Operator",
        role: str = "operator",
    ) -> dict[str, Any]:
        # Clear client cookies before registering a distinct test identity cleanly.
        client.cookies.clear()
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
                "role": role,
            },
        )
        assert res.status_code == 201, res.text
        data = res.json()
        client.cookies.clear()
        return {
            "user": data["user"],
            "access_token": data["access_token"],
            "csrf_token": data["csrf_token"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"},
        }

    return _register
