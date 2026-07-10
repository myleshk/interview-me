"""Qdrant vector store connection & query helpers.

Provides a singleton client and high-level functions for:
- Creating / ensuring collections exist
- Querying with hybrid search

Note: indexing (upsert) lives in the top-level ``indexer/`` component in this
repo and reads curated content from the separate data repo. The API is a
read-only Qdrant consumer.

Requires Qdrant to be running (see ``docker-compose.yml``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    SparseVectorParams,
    VectorParams,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResponse:
    """Retrieved payloads plus metadata-filter diagnostics."""

    payloads: list[dict[str, Any]]
    filtered_domains: tuple[str, ...]
    filter_fallback: bool

# ── Singleton client ───────────────────────────────────────

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Return (or create) the async Qdrant client singleton."""
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        _client = AsyncQdrantClient(**kwargs)
    return _client


# ── Collection management ──────────────────────────────────


async def ensure_collection() -> None:
    """Create the collection if it doesn't already exist.

    Enables both dense vectors and sparse vectors
    (BM25-style) for Qdrant hybrid search.

    If Qdrant is unreachable (e.g. still starting up), logs a
    warning instead of crashing the app. The collection will be
    created on the first successful search request instead.
    """
    client = get_qdrant_client()
    try:
        collections = await client.get_collections()
    except Exception as exc:
        logger.warning(
            "qdrant | unreachable during startup (%s) — "
            "collection will be ensured on first request",
            exc,
        )
        return

    names = [c.name for c in collections.collections]

    if settings.qdrant_collection_name in names:
        logger.info("qdrant | collection '%s' already exists", settings.qdrant_collection_name)
        return

    await client.create_collection(
        collection_name=settings.qdrant_collection_name,
        vectors_config=VectorParams(
            size=settings.embedding_dim,
            distance=Distance.COSINE,
        ),
        sparse_vectors_config={
            "bm25": SparseVectorParams(),
        },
    )
    logger.info("qdrant | created collection '%s'", settings.qdrant_collection_name)


# ── Hybrid search ─────────────────────────────────────────


async def hybrid_search(
    query_vector: list[float],
    sparse_vector: dict[int, float] | None = None,
    limit: int = 5,
    domains: list[str] | None = None,
) -> SearchResponse:
    """Perform a hybrid (dense + sparse) search.

    Args:
        query_vector: Dense embedding vector.
        sparse_vector: Optional BM25 sparse vector.
        limit: Max number of results.

    Returns:
        Payloads and diagnostics describing metadata filtering.
    """
    client = get_qdrant_client()

    # Ensure collection exists (handles the case where startup ensure
    # failed because Qdrant wasn't ready yet).
    try:
        await ensure_collection()
    except Exception:
        logger.debug("hybrid_search | ensure_collection failed (may already exist)")

    filtered_domains = tuple(dict.fromkeys(domains or []))
    query_filter = None
    if filtered_domains:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="document_metadata.domains",
                    match=MatchAny(any=list(filtered_domains)),
                )
            ]
        )

    async def _query(active_filter: Filter | None):
        return await client.query_points(
            collection_name=settings.qdrant_collection_name,
            query=query_vector,
            using="",  # default vector field
            query_filter=active_filter,
            limit=limit,
            with_payload=True,
        )

    # Build the search query — dense only for now; sparse added when indexer is wired.
    results = await _query(query_filter)
    filter_fallback = False
    if query_filter is not None and not results.points:
        logger.debug(
            "hybrid_search | metadata filter returned no results; retrying unfiltered domains=%s",
            filtered_domains,
        )
        results = await _query(None)
        filter_fallback = True

    return SearchResponse(
        payloads=[point.payload or {} for point in results.points],
        filtered_domains=filtered_domains,
        filter_fallback=filter_fallback,
    )
