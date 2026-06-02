"""Markdown-to-vector indexer.

Reads ``api/data/knowledge/*.md`` files, chunks them, generates
embeddings via FastEmbed, and upserts them into Qdrant for hybrid search.

Usage (one-time or on-deploy)::

    python -m app.ai.indexer

Or call ``await index_all()`` from the FastAPI lifespan.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastembed import TextEmbedding

from app.core.config import settings
from app.ai.qdrant import ensure_collection, upsert_points

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge"
CHUNK_SIZE = 500  # characters per chunk (naive split)
CHUNK_OVERLAP = 50


# ── Chunking ──────────────────────────────────────────────


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Naive character-level chunking with overlap."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return [c for c in chunks if c]


def _load_markdown_files() -> list[dict[str, str]]:
    """Read all .md files from the data directory."""
    docs: list[dict[str, str]] = []
    if not DATA_DIR.exists():
        logger.warning("indexer | data dir not found: %s", DATA_DIR)
        return docs

    for path in sorted(DATA_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if text.strip():
            docs.append({"source": path.name, "text": text})

    logger.info("indexer | loaded %d markdown files", len(docs))
    return docs


# ── Embedding ─────────────────────────────────────────────

_model: TextEmbedding | None = None


def _get_embedding_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=settings.embedding_model_name)
    return _model


def _embed(texts: list[str]) -> list[list[float]]:
    """Generate dense embeddings via FastEmbed (local, no API call)."""
    model = _get_embedding_model()
    return list(model.embed(texts))


# ── Main entry point ──────────────────────────────────────


async def index_all() -> int:
    """Parse all Markdown files, embed, and upsert into Qdrant.

    Returns:
        Number of chunks indexed.
    """
    from qdrant_client.models import PointStruct

    await ensure_collection()

    docs = _load_markdown_files()
    if not docs:
        logger.info("indexer | nothing to index")
        return 0

    # Flatten into chunks, keeping source metadata
    all_chunks: list[dict[str, str]] = []
    for doc in docs:
        for chunk in _chunk_text(doc["text"]):
            all_chunks.append({"source": doc["source"], "text": chunk})

    logger.info("indexer | %d chunks from %d files", len(all_chunks), len(docs))

    # Embed all chunks
    texts = [c["text"] for c in all_chunks]
    vectors = _embed(texts)

    # Build Qdrant points
    points = [
        PointStruct(
            id=i,
            vector=vec.tolist() if hasattr(vec, "tolist") else vec,
            payload={"source": all_chunks[i]["source"], "text": all_chunks[i]["text"]},
        )
        for i, vec in enumerate(vectors)
    ]

    await upsert_points(points)
    logger.info("indexer | indexed %d points into '%s'", len(points), settings.qdrant_collection_name)
    return len(points)


# ── CLI entry point ────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    count = asyncio.run(index_all())
    print(f"Indexed {count} chunks into '{settings.qdrant_collection_name}'")
