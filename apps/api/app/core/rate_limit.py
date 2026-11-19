"""In-memory sliding-window rate limiter for authentication endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import Settings
from app.core.exceptions import RateLimitError


class SlidingWindowRateLimiter:
    """Thread-safe per-key sliding-window rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
                raise RateLimitError(retry_after_seconds=retry_after)

            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


auth_rate_limiter = SlidingWindowRateLimiter()


def extract_client_ip(request: Request) -> str:
    """Resolve best-effort client IP for rate limiting and audit metadata."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_auth_rate_limit(request: Request, settings: Settings, scope: str) -> None:
    """Enforce configured sliding-window rate limit on sensitive auth routes."""
    client_ip = extract_client_ip(request)
    key = f"{scope}:{client_ip}"
    auth_rate_limiter.check(
        key=key,
        max_requests=settings.auth_rate_limit_requests,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
