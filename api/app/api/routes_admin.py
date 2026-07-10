"""Admin routes — ``/v1/health``, ``/v1/metrics``, and ``/v1/debug/retrieve``."""

from __future__ import annotations

from time import monotonic
from typing import Any

import httpx
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


# ── POST /v1/debug/retrieve ──────────────────────────────


class RetrieveDebugRequest(BaseModel):
    query: str
    limit: int = 5


class RetrieveChunk(BaseModel):
    source: str
    text: str
    document_metadata: dict[str, Any]
    section_path: str
    section_headings: list[str]


class RetrievalClassification(BaseModel):
    domains: list[str]
    matched_terms: dict[str, list[str]]
    filter_fallback: bool


class RetrieveDebugResponse(BaseModel):
    query: str
    total_results: int
    classification: RetrievalClassification
    chunks: list[RetrieveChunk]


@router.post(
    "/debug/retrieve",
    response_model=RetrieveDebugResponse,
    summary="Debug: run the RAG retrieve step standalone",
)
async def debug_retrieve(body: RetrieveDebugRequest) -> RetrieveDebugResponse:
    """Run only the ``retrieve()`` pipeline — embed, search Qdrant,
    return raw chunks — without calling the LLM.

    Useful for iterating on your ``data/knowledge/*.md`` content and
    verifying which chunks surface for a given query.
    """
    from app.ai.qdrant import hybrid_search
    from app.ai.retrieval import classify_query

    # Call the remote embedding service
    resp = httpx.post(
        f"{settings.embedding_service_url}/v1/embeddings",
        json={"input": body.query},
        timeout=httpx.Timeout(30.0),
    )
    resp.raise_for_status()
    query_vector = list(resp.json()["data"][0]["embedding"])

    classification = classify_query(body.query)
    search = await hybrid_search(
        query_vector=query_vector,
        limit=body.limit,
        domains=list(classification.domains),
    )
    results = search.payloads

    chunks = [
        RetrieveChunk(
            source=r.get("source", "?"),
            text=r.get("text", ""),
            document_metadata=r.get("document_metadata", {}),
            section_path=r.get("section_path", ""),
            section_headings=r.get("section_headings", []),
        )
        for r in results
        if r.get("text")
    ]

    return RetrieveDebugResponse(
        query=body.query,
        total_results=len(results),
        classification=RetrievalClassification(
            domains=list(classification.domains),
            matched_terms={
                domain: list(terms)
                for domain, terms in classification.matched_terms.items()
            },
            filter_fallback=search.filter_fallback,
        ),
        chunks=chunks,
    )
