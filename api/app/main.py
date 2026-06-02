"""interview-me API — FastAPI application entry-point.

Run locally (from the ``api/`` directory)::

    uvicorn app.main:app --reload

All routers are registered here and wired together.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.workflows import AvatarWorkflow
from app.ai.qdrant import ensure_collection
from app.api.routes_admin import router as admin_router
from app.api.routes_ai import router as ai_router
from app.api.routes_cv import router as cv_router
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Lifespan ────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hooks."""
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # Pre-warm the workflow (shared across requests)
    app.state.workflow = AvatarWorkflow()
    app.state.request_count = 0

    # Ensure the Qdrant collection exists (idempotent — no-op if already there)
    await ensure_collection()

    logger.info(
        "interview-me API started  model=%s  qdrant=%s",
        settings.deepseek_model,
        settings.qdrant_url,
    )
    yield
    logger.info("interview-me API shutting down")


# ── App instance ────────────────────────────────────────────

app = FastAPI(
    title="interview-me API",
    version="0.2.0",
    lifespan=lifespan,
)

# ── Middleware ──────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request counter middleware ──────────────────────────────


@app.middleware("http")
async def count_requests(request: Request, call_next):
    """Increment a simple request counter for the /metrics endpoint."""
    response = await call_next(request)
    app.state.request_count = getattr(app.state, "request_count", 0) + 1
    return response


# ── Routers ────────────────────────────────────────────────

app.include_router(ai_router)
app.include_router(admin_router)
app.include_router(cv_router)
