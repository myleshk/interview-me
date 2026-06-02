"""Admin routes — ``/v1/health`` and ``/v1/metrics``."""

from __future__ import annotations

from time import monotonic

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/v1", tags=["Admin"])

# ── Uptime tracker ────────────────────────────────────────

_start_time: float = monotonic()


# ── Schemas ────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    model: str
    uptime_seconds: float


class MetricsResponse(BaseModel):
    total_requests: int
    uptime_seconds: float
    model: str


# ── GET /v1/health ────────────────────────────────────────


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness / readiness probe",
)
async def health() -> HealthResponse:
    return HealthResponse(
        model=settings.deepseek_model,
        uptime_seconds=monotonic() - _start_time,
    )


# ── GET /v1/metrics ───────────────────────────────────────


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Basic usage metrics",
)
async def metrics(request: Request) -> MetricsResponse:
    total = getattr(request.app.state, "request_count", 0)
    return MetricsResponse(
        total_requests=total,
        uptime_seconds=monotonic() - _start_time,
        model=settings.deepseek_model,
    )
