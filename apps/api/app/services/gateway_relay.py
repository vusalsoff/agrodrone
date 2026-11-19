"""Bounded in-memory live frame relay buffer, replay guard, and gateway health helpers."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import generate_opaque_token, hash_opaque_token
from app.models.edge_gateway import EdgeGateway, StreamSession
from app.schemas.gateway import GatewayRead


@dataclass(frozen=True)
class BufferedFrame:
    jpeg_bytes: bytes
    received_at: datetime
    sequence: int
    session_id: uuid.UUID


class BoundedFrameRelayStore:
    """Stores strictly the latest JPEG frame per active gateway (zero unbounded memory)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: dict[str, BufferedFrame] = {}

    def put_frame(
        self,
        gateway_id: uuid.UUID,
        *,
        session_id: uuid.UUID,
        jpeg_bytes: bytes,
        sequence: int = 0,
    ) -> BufferedFrame:
        frame = BufferedFrame(
            jpeg_bytes=jpeg_bytes,
            received_at=datetime.now(UTC),
            sequence=sequence,
            session_id=session_id,
        )
        with self._lock:
            self._frames[str(gateway_id)] = frame
        return frame

    def get_latest(self, gateway_id: uuid.UUID) -> BufferedFrame | None:
        with self._lock:
            return self._frames.get(str(gateway_id))

    def clear(self, gateway_id: uuid.UUID) -> None:
        with self._lock:
            self._frames.pop(str(gateway_id), None)

    def reset_all(self) -> None:
        with self._lock:
            self._frames.clear()


class GatewayReplayGuard:
    """Sliding-window nonce tracker preventing replay of signed/stamped gateway requests."""

    def __init__(self, ttl_seconds: int = 300, max_entries_per_gateway: int = 2048) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries_per_gateway
        self._lock = threading.Lock()
        self._seen: dict[str, dict[str, float]] = {}

    def verify_and_record(
        self,
        gateway_id: str,
        *,
        timestamp_header: str | None,
        nonce_header: str | None,
    ) -> None:
        if not timestamp_header and not nonce_header:
            return

        now = time.time()
        if timestamp_header:
            try:
                ts = float(timestamp_header)
            except ValueError as exc:
                raise AuthenticationError("Invalid X-Gateway-Timestamp header.") from exc
            if abs(now - ts) > self._ttl:
                raise AuthenticationError("Gateway request timestamp outside allowed replay window.")

        if nonce_header:
            with self._lock:
                bucket = self._seen.setdefault(gateway_id, {})
                expired = [k for k, exp in bucket.items() if exp <= now]
                for k in expired:
                    del bucket[k]
                if nonce_header in bucket:
                    raise AuthenticationError("Replay detected: duplicate X-Gateway-Nonce.")
                if len(bucket) >= self._max:
                    oldest_key = min(bucket, key=lambda k: bucket[k])
                    del bucket[oldest_key]
                bucket[nonce_header] = now + self._ttl

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()


frame_relay_store = BoundedFrameRelayStore()
gateway_replay_guard = GatewayReplayGuard()


def generate_gateway_credential() -> tuple[str, str, str]:
    """Return (plaintext_token, credential_prefix, sha256_hash)."""
    raw = f"agw_{generate_opaque_token(36)}"
    prefix = raw[:12]
    digest = hash_opaque_token(raw)
    return raw, prefix, digest


def compute_gateway_liveness(gateway: EdgeGateway, settings: Settings) -> tuple[bool, int | None]:
    """Compute real gateway liveness from authenticated heartbeat age; never fabricated."""
    if gateway.status == "revoked" or gateway.last_heartbeat_at is None:
        return False, None

    last_hb = gateway.last_heartbeat_at
    if last_hb.tzinfo is None:
        last_hb = last_hb.replace(tzinfo=UTC)
    age = max(0, int((datetime.now(UTC) - last_hb).total_seconds()))
    is_live = gateway.status == "active" and age <= settings.gateway_heartbeat_ttl_seconds
    return is_live, age


def to_gateway_read(gateway: EdgeGateway, settings: Settings) -> GatewayRead:
    is_live, age = compute_gateway_liveness(gateway, settings)
    base = GatewayRead.model_validate(gateway)
    return base.model_copy(update={"is_live": is_live, "heartbeat_age_seconds": age})


def is_stream_session_active(session: StreamSession, now: datetime | None = None) -> bool:
    if session.status != "active":
        return False
    ref = now or datetime.now(UTC)
    exp = session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    return exp > ref
