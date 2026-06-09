"""Standalone knowledge indexer for interview-me.

Reads ``knowledge/*.md`` files, chunks them with LlamaIndex's
hierarchical ``MarkdownNodeParser`` (respects heading structure),
generates embeddings via the embedding microservice, and upserts
them into Qdrant for hybrid search.

Usage::

    python main.py                        # from interview-me/indexer/
    docker run ... interview-me-indexer   # via Docker
    kubectl create job ...                # K8s Job

Environment variables
---------------------
- ``QDRANT_URL`` — Qdrant REST API (default: ``http://localhost:6333``)
- ``QDRANT_COLLECTION_NAME`` — collection name (default: ``interview_me``)
- ``EMBEDDING_SERVICE_URL`` — embedding service (default: ``http://localhost:8080``)
- ``EMBEDDING_DIM`` — vector dimension (default: ``384``)
- ``DATA_DIR`` — path to knowledge .md files (default: sibling ``../data/knowledge`` repo clone)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

import httpx
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

# ── Config (all from env, sensible defaults) ────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION_NAME", "interview_me")
EMBEDDING_SERVICE_URL = os.environ.get("EMBEDDING_SERVICE_URL", "http://localhost:8080")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))

# Default DATA_DIR: sibling ``data/knowledge`` repo next to the code repo
_DATA_DEFAULT = str(Path(__file__).resolve().parent.parent.parent / "data" / "knowledge")
DATA_DIR = Path(os.environ.get("DATA_DIR", _DATA_DEFAULT))

logger = logging.getLogger("indexer")


# ── Qdrant helpers ─────────────────────────────────────────


async def _ensure_collection(client: AsyncQdrantClient) -> None:
    """Create the collection if it doesn't exist."""
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if QDRANT_COLLECTION_NAME in names:
        logger.info("collection '%s' already exists", QDRANT_COLLECTION_NAME)
        return
    await client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    logger.info("created collection '%s'", QDRANT_COLLECTION_NAME)


async def _list_indexed_sources(client: AsyncQdrantClient) -> set[str]:
    """Return all known ``source`` payload values in the collection."""
    sources: set[str] = set()
    offset = None

    while True:
        records, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION_NAME,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for record in records:
            payload = record.payload or {}
            source = payload.get("source")
            if isinstance(source, str) and source:
                sources.add(source)
        if offset is None:
            break

    return sources


async def _delete_source_points(client: AsyncQdrantClient, source: str) -> None:
    """Delete all points belonging to a single Markdown source file."""
    await client.delete(
        collection_name=QDRANT_COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value=source),
                )
            ]
        ),
    )
    logger.info("deleted existing points for source '%s'", source)


# ── Markdown loading ───────────────────────────────────────


def _load_markdown_files() -> list[Document]:
    """Read all .md files as LlamaIndex Documents (skip README.md)."""
    docs: list[Document] = []
    if not DATA_DIR.exists():
        logger.warning("data dir not found: %s", DATA_DIR)
        return docs
    for path in sorted(DATA_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        if text.strip():
            docs.append(Document(text=text, metadata={"source": path.name}))
    logger.info("loaded %d markdown files", len(docs))
    return docs


# ── Embedding via remote service ───────────────────────────


def _embed(texts: list[str]) -> list[list[float]]:
    """Generate dense embeddings via the remote embedding service."""
    resp = httpx.post(
        f"{EMBEDDING_SERVICE_URL}/v1/embeddings",
        json={"input": texts},
        timeout=httpx.Timeout(60.0),
    )
    resp.raise_for_status()
    body = resp.json()
    items = sorted(body["data"], key=lambda d: d["index"])
    return [item["embedding"] for item in items]


def _point_id(source: str, text: str) -> int:
    """Build a stable 64-bit point id from source filename and chunk text."""
    digest = hashlib.sha256(f"{source}\0{text}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


# ── Main entry point ───────────────────────────────────────


async def index_all() -> int:
    """Parse all Markdown files, embed, and upsert into Qdrant.

    Returns:
        Number of chunks indexed.
    """
    client = AsyncQdrantClient(url=QDRANT_URL)

    try:
        # 1. Ensure the collection exists, but keep existing data intact.
        await _ensure_collection(client)

        # 2. Load markdown files
        documents = _load_markdown_files()
        if not documents:
            logger.info("nothing to index")
            return 0

        # 3. Hierarchical Markdown parsing
        parser = MarkdownNodeParser()
        nodes = parser.get_nodes_from_documents(documents)
        logger.info(
            "%d chunks from %d files (MarkdownNodeParser)",
            len(nodes),
            len(documents),
        )

        # 4. Extract texts
        texts = [node.get_content() for node in nodes]

        # Optional size summary
        sizes = [len(t) for t in texts]
        logger.debug(
            "chunk sizes: min=%d  avg=%d  max=%d",
            min(sizes) if sizes else 0,
            sum(sizes) // len(sizes) if sizes else 0,
            max(sizes) if sizes else 0,
        )

        # 5. Remove existing points for managed sources, including deleted files.
        current_sources = {doc.metadata.get("source", "?") for doc in documents}
        existing_sources = await _list_indexed_sources(client)
        stale_sources = existing_sources - current_sources
        sources_to_delete = sorted(current_sources | stale_sources)
        for source in sources_to_delete:
            await _delete_source_points(client, source)

        # 6. Embed
        vectors = _embed(texts)

        # 7. Upsert with stable ids so the collection remains persistent.
        points = [
            PointStruct(
                id=_point_id(nodes[i].metadata.get("source", "?"), nodes[i].get_content()),
                vector=vec.tolist() if hasattr(vec, "tolist") else vec,
                payload={
                    "source": nodes[i].metadata.get("source", "?"),
                    "text": nodes[i].get_content(),
                },
            )
            for i, vec in enumerate(vectors)
        ]
        await client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=points,
        )
        logger.info(
            "indexed %d points into '%s'",
            len(points),
            QDRANT_COLLECTION_NAME,
        )
        return len(points)
    finally:
        await client.close()


# ── CLI entry point ────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    count = asyncio.run(index_all())
    print(f"Indexed {count} chunks into '{QDRANT_COLLECTION_NAME}'")
