"""Outbound authenticated HTTP client from Field Edge Gateway to AgroDrone FastAPI."""

from __future__ import annotations

import secrets
import time
from typing import Any

import httpx

from agrodrone_gateway.config import GatewayConfig


class GatewayApiClient:
    """Communicates exclusively outbound over HTTP/HTTPS using X-Gateway-Token + replay headers."""

    def __init__(self, config: GatewayConfig, transport: httpx.BaseTransport | None = None) -> None:
        self._cfg = config
        self._client = httpx.Client(
            base_url=config.api_base_url,
            timeout=httpx.Timeout(
                connect=config.connect_timeout_seconds,
                read=config.read_timeout_seconds,
                write=config.read_timeout_seconds,
                pool=config.connect_timeout_seconds,
            ),
            transport=transport,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-Gateway-Token": self._cfg.gateway_token,
            "X-Gateway-Timestamp": f"{time.time():.3f}",
            "X-Gateway-Nonce": secrets.token_hex(16),
        }

    def send_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        res = self._client.post(
            "/api/v1/gateway/heartbeat",
            headers=self._auth_headers(),
            json=payload,
        )
        res.raise_for_status()
        return dict(res.json())

    def push_stream_frame(self, jpeg_bytes: bytes, *, sequence: int) -> dict[str, Any]:
        res = self._client.post(
            "/api/v1/gateway/stream/frame",
            headers=self._auth_headers(),
            files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
            data={"sequence": str(sequence)},
        )
        res.raise_for_status()
        return dict(res.json())

    def upload_snapshot(
        self,
        jpeg_bytes: bytes,
        *,
        filename: str = "esp32_snapshot.jpg",
        notes: str | None = None,
        analyze: bool = False,
        model_id: str = "yolov8n-coco-general",
        confidence_threshold: float = 0.35,
    ) -> dict[str, Any]:
        data: dict[str, str] = {
            "analyze": "true" if analyze else "false",
            "model_id": model_id,
            "confidence_threshold": str(confidence_threshold),
        }
        if notes:
            data["notes"] = notes
        res = self._client.post(
            "/api/v1/gateway/snapshots",
            headers=self._auth_headers(),
            files={"file": (filename, jpeg_bytes, "image/jpeg")},
            data=data,
        )
        res.raise_for_status()
        return dict(res.json())

    def get_latest_detection(self, *, model_id: str | None = None) -> dict[str, Any]:
        params = {"model_id": model_id} if model_id else None
        res = self._client.get(
            "/api/v1/gateway/latest-detection",
            headers=self._auth_headers(),
            params=params,
        )
        res.raise_for_status()
        return dict(res.json())

    def close(self) -> None:
        self._client.close()
