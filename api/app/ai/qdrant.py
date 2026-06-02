"""Qdrant vector store connection & query helpers.

Provides a singleton client and high-level functions for:
- Creating / ensuring collections exist
- Upserting points with dense + sparse vectors (hybrid search)
- Querying with hybrid search

Requires Qdrant to be running (see ``docker-compose.yml``).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Singleton client ───────────────────────────────────────

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Return (or create) the async Qdrant client singleton."""
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
    return _client


# ── Collection management ──────────────────────────────────


async def ensure_collection() -> None:
    """Create the collection if it doesn't already exist.

    Enables both dense vectors (FastEmbed) and sparse vectors
    (BM25-style) for Qdrant hybrid search.
    """
    client = get_qdrant_client()
    collections = await client.get_collections()
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


# ── Upsert ────────────────────────────────────────────────


async def upsert_points(
    points: list[PointStruct],
) -> None:
    """Batch-upsert points into the avatar collection."""
    client = get_qdrant_client()
    await client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=points,
    )
    logger.info("qdrant | upserted %d points", len(points))


# ── Hybrid search ─────────────────────────────────────────


async def hybrid_search(
    query_vector: list[float],
    sparse_vector: dict[int, float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Perform a hybrid (dense + sparse) search.

    Args:
        query_vector: Dense embedding from FastEmbed.
        sparse_vector: Optional BM25 sparse vector.
        limit: Max number of results.

    Returns:
        List of payload dicts from matching points.
    """
    client = get_qdrant_client()

    # Build the search query — dense only for now; sparse added when indexer is wired.
    results = await client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        using="",  # default vector field
        limit=limit,
        with_payload=True,
    )

    return [point.payload or {} for point in results.points]
