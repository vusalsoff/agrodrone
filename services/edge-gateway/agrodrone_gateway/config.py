"""Configuration for the standalone ESP32-CAM Field Edge Gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DeploymentMode = Literal["local_dev", "remote_cloud"]


@dataclass(frozen=True)
class GatewayConfig:
    api_base_url: str
    gateway_token: str
    esp32_base_url: str = "http://192.168.4.1"
    esp32_stream_url: str = "http://192.168.4.1:81/stream"
    deployment_mode: DeploymentMode = "local_dev"
    target_fps: float = 2.0
    snapshot_interval_seconds: float = 15.0
    max_frame_bytes: int = 512 * 1024
    connect_timeout_seconds: float = 4.0
    read_timeout_seconds: float = 8.0
    heartbeat_interval_seconds: float = 5.0
    backoff_initial_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    upload_retry_limit: int = 5
    offline_spool_dir: Path = Path("./data/gateway_spool")
    offline_quota_bytes: int = 100 * 1024 * 1024
    local_interface: str | None = None
    uplink_interface: str | None = None

    @classmethod
    def from_env(cls) -> GatewayConfig:
        mode_raw = os.environ.get("AGRODRONE_DEPLOYMENT_MODE", "local_dev").strip()
        mode: DeploymentMode = "remote_cloud" if mode_raw == "remote_cloud" else "local_dev"
        return cls(
            api_base_url=os.environ.get("AGRODRONE_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            gateway_token=os.environ.get("AGRODRONE_GATEWAY_TOKEN", "").strip(),
            esp32_base_url=os.environ.get("ESP32_BASE_URL", "http://192.168.4.1").rstrip("/"),
            esp32_stream_url=os.environ.get("ESP32_STREAM_URL", "http://192.168.4.1:81/stream"),
            deployment_mode=mode,
            target_fps=max(0.2, min(5.0, float(os.environ.get("GATEWAY_TARGET_FPS", "2.0")))),
            snapshot_interval_seconds=max(
                0.0, float(os.environ.get("GATEWAY_SNAPSHOT_INTERVAL_SECONDS", "15.0"))
            ),
            max_frame_bytes=max(
                32768, min(2 * 1024 * 1024, int(os.environ.get("GATEWAY_MAX_FRAME_BYTES", str(512 * 1024))))
            ),
            connect_timeout_seconds=float(os.environ.get("GATEWAY_CONNECT_TIMEOUT", "4.0")),
            read_timeout_seconds=float(os.environ.get("GATEWAY_READ_TIMEOUT", "8.0")),
            heartbeat_interval_seconds=float(os.environ.get("GATEWAY_HEARTBEAT_INTERVAL", "5.0")),
            upload_retry_limit=max(1, int(os.environ.get("GATEWAY_UPLOAD_RETRY_LIMIT", "5"))),
            offline_spool_dir=Path(os.environ.get("GATEWAY_SPOOL_DIR", "./data/gateway_spool")),
            offline_quota_bytes=max(
                1024 * 1024, int(os.environ.get("GATEWAY_OFFLINE_QUOTA_BYTES", str(100 * 1024 * 1024)))
            ),
            local_interface=os.environ.get("GATEWAY_LOCAL_INTERFACE") or None,
            uplink_interface=os.environ.get("GATEWAY_UPLINK_INTERFACE") or None,
        )
