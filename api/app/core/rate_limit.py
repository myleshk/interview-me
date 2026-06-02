"""Simple in-memory rate limiter.

Uses a sliding-window counter keyed by client IP.
Suitable for single-instance deployments; for multi-pod production
replace with Redis-backed rate limiting.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import settings


class _SlidingWindowLimiter:
    """In-memory sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        """Raise 429 if the client has exceeded the rate limit."""
        key = self._key(request)
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Prune expired entries
        self._buckets[key] = [
            ts for ts in self._buckets[key] if ts > window_start
        ]

        if len(self._buckets[key]) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
            )

        self._buckets[key].append(now)


# Module-level singleton — configured from settings on first import.
_limiter = _SlidingWindowLimiter(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


async def rate_limit(request: Request) -> None:
    """FastAPI dependency that enforces per-IP rate limiting."""
    _limiter.check(request)
