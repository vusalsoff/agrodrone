"""Environment-based application configuration powered by Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AgroDrone API"
    app_version: str = "0.3.0"
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # PostgreSQL in production/Docker; SQLite supported for zero-Docker local development & tests.
    database_url: str = "sqlite:///./data/agrodrone_dev.db"
    database_echo: bool = False
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout: int = Field(default=30, ge=5, le=120)
    db_pool_recycle: int = Field(default=1800, ge=60, le=7200)

    # Authentication, cookies, CSRF & rate limiting
    jwt_secret_key: str = "local-dev-only-secret-change-before-production-32chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    access_cookie_name: str = "agrodrone_access_token"
    refresh_cookie_name: str = "agrodrone_refresh_token"
    csrf_cookie_name: str = "agrodrone_csrf_token"
    csrf_header_name: str = "X-CSRF-Token"

    auth_rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=5, le=3600)

    # S3-compatible object storage (MinIO in Docker, AWS S3 / R2 / GCS in production)
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = "./data/storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_media: str = "agrodrone-media"
    s3_region: str = "us-east-1"
    s3_presign_expire_seconds: int = Field(default=300, ge=30, le=3600)

    # Media upload limits (bytes)
    max_image_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    max_video_upload_bytes: int = Field(default=150 * 1024 * 1024, ge=1024)

    # AI Inference (Phase 3 AgroVision Engine)
    ai_inference_enabled: bool = True
    ai_model_profile: str = "yolov8n-coco-general"
    ai_model_weights_path: str = ""
    ai_device: str = "cpu"
    ai_confidence_threshold: float = Field(default=0.35, ge=0.05, le=0.99)
    max_video_duration_seconds: int = Field(default=120, ge=5, le=600)
    max_video_sampled_frames: int = Field(default=60, ge=1, le=120)
    default_frame_sample_interval_ms: int = Field(default=1000, ge=200, le=10000)
    # inline_thread: API process runs jobs on a bounded thread pool (local dev).
    # external: API only enqueues; a separate `python -m app.worker` process claims jobs (production).
    ai_worker_mode: Literal["inline_thread", "external"] = "inline_thread"
    ai_weights_dir: str = ""
    ai_max_job_attempts: int = Field(default=3, ge=1, le=10)
    ai_worker_poll_seconds: float = Field(default=2.0, ge=0.2, le=60.0)

    # ESP32-CAM & Field Edge Gateway Policy (Phase 4)
    esp32_default_ap_ssid: str = "agroDrone"
    esp32_default_base_url: str = "http://192.168.4.1"
    esp32_default_stream_url: str = "http://192.168.4.1:81/stream"
    allow_direct_local_camera_probe: bool = False
    edge_gateway_enabled: bool = True
    gateway_heartbeat_ttl_seconds: int = Field(default=30, ge=5, le=300)
    gateway_max_frame_bytes: int = Field(default=2 * 1024 * 1024, ge=65536, le=10 * 1024 * 1024)
    gateway_max_stream_subscribers: int = Field(default=4, ge=1, le=20)
    gateway_stream_session_ttl_seconds: int = Field(default=600, ge=30, le=3600)

    # Optional SMTP Email Notifications (Phase 5 — unavailable unless configured)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Phase 6 Production Observability & Storage Hardening
    s3_use_iam_role: bool = False
    sentry_dsn: str = ""
    ai_worker_concurrency: int = Field(default=1, ge=1, le=16)
    # Local desktop convenience only: auto-authenticates local operator without login screen.
    # Strictly forbidden when environment == "production".
    local_no_auth_mode: bool = False

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from_email.strip())

    @model_validator(mode="after")
    def validate_production_hardening(self) -> "Settings":
        if self.environment == "production":
            insecure_markers = (
                "local-dev-only",
                "replace-with-",
                "dev-only-change",
                "change-me",
            )
            lowered = self.jwt_secret_key.lower()
            if any(marker in lowered for marker in insecure_markers):
                raise ValueError(
                    "Production environment cannot start with a development placeholder JWT_SECRET_KEY."
                )
            if "*" in self.cors_origins:
                raise ValueError("Production CORS_ORIGINS cannot contain wildcard '*'.")
            if self.allow_direct_local_camera_probe:
                raise ValueError(
                    "ALLOW_DIRECT_LOCAL_CAMERA_PROBE must be false in production (SSRF protection)."
                )
            if (
                self.storage_backend == "s3"
                and not self.s3_use_iam_role
                and (not self.s3_access_key_id.strip() or not self.s3_secret_access_key.strip())
            ):
                raise ValueError(
                    "Production S3 storage requires S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY (or S3_USE_IAM_ROLE=true)."
                )
            if self.local_no_auth_mode:
                raise ValueError("LOCAL_NO_AUTH_MODE cannot be enabled in production.")
        return self

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_secret_strength(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long.")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_secure_cookies(self) -> bool:
        return self.cookie_secure or self.is_production

    @property
    def database_dialect(self) -> str:
        if self.database_url.startswith("postgresql"):
            return "postgresql"
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        return self.database_url.split(":", 1)[0]

    def ensure_local_directories(self) -> None:
        """Ensure local SQLite and local media storage directories exist when used."""
        if self.database_url.startswith("sqlite:///") and ":memory:" not in self.database_url:
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.storage_backend == "local":
            Path(self.local_storage_path).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached runtime settings instance."""
    return Settings()
