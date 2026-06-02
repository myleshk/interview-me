"""Markdown-to-vector indexer.

Reads ``api/data/knowledge/*.md`` files, chunks them with LlamaIndex's
hierarchical ``MarkdownNodeParser`` (respects heading structure), generates
embeddings via FastEmbed, and upserts them into Qdrant for hybrid search.

Usage (one-time or on-deploy)::

    python -m app.ai.indexer

Or call ``await index_all()`` from the FastAPI lifespan.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastembed import TextEmbedding
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

from app.core.config import settings
from app.ai.qdrant import ensure_collection, upsert_points

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge"

# ── Markdown loading ──────────────────────────────────────


def _load_markdown_files() -> list[Document]:
    """Read all .md files as LlamaIndex Documents (skip README.md template)."""
    docs: list[Document] = []
    if not DATA_DIR.exists():
        logger.warning("indexer | data dir not found: %s", DATA_DIR)
        return docs

    for path in sorted(DATA_DIR.glob("*.md")):
        if path.name == "README.md":
            continue  # template, not personal knowledge
        text = path.read_text(encoding="utf-8")
        if text.strip():
            docs.append(Document(text=text, metadata={"source": path.name}))

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
    """Parse all Markdown files with hierarchical heading-aware chunking,
    embed, and upsert into Qdrant.

    Returns:
        Number of chunks indexed.
    """
    from qdrant_client.models import PointStruct

    await ensure_collection()

    documents = _load_markdown_files()
    if not documents:
        logger.info("indexer | nothing to index")
        return 0

    # Hierarchical Markdown parsing — chunks respect heading structure
    parser = MarkdownNodeParser()
    nodes = parser.get_nodes_from_documents(documents)

    logger.info(
        "indexer | %d chunks from %d files (MarkdownNodeParser)",
        len(nodes),
        len(documents),
    )

    # Extract texts for embedding
    texts = [node.get_content() for node in nodes]

    # Optional: log a size summary
    sizes = [len(t) for t in texts]
    logger.debug(
        "indexer | chunk sizes: min=%d  avg=%d  max=%d",
        min(sizes) if sizes else 0,
        sum(sizes) // len(sizes) if sizes else 0,
        max(sizes) if sizes else 0,
    )

    vectors = _embed(texts)

    # Build Qdrant points with enriched metadata
    points = [
        PointStruct(
            id=i,
            vector=vec.tolist() if hasattr(vec, "tolist") else vec,
            payload={
                "source": nodes[i].metadata.get("source", "?"),
                "text": nodes[i].get_content(),
            },
        )
        for i, vec in enumerate(vectors)
    ]

    await upsert_points(points)
    logger.info(
        "indexer | indexed %d points into '%s'",
        len(points),
        settings.qdrant_collection_name,
    )
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
