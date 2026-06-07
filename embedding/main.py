"""Embedding microservice — loads FastEmbed once, serves over HTTP.

Single model, single process, no GPU needed.
Exposes POST /v1/embeddings (OpenAI-compatible subset).

Production use with uvicorn:
    uvicorn main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────

MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")
PORT = int(os.getenv("PORT", "8080"))

logger = logging.getLogger(__name__)

# ── App & Model (loaded once at startup) ──────────────────

app = FastAPI(title="embedding-service", version="1.0.0")
model: TextEmbedding

# ── Request / Response ────────────────────────────────────


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible subset: supports single string or list."""

    input: str | list[str]
    model: str = "bge-small-en-v1.5"  # ignored, single model


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: dict | None = None


# ── Startup ───────────────────────────────────────────────


@app.on_event("startup")
async def load_model() -> None:
    global model
    logger.info("Loading embedding model: %s", MODEL_NAME)
    model = TextEmbedding(model_name=MODEL_NAME)
    # Warm up — force download + ONNX load
    _ = list(model.embed(["warmup"]))
    logger.info("Embedding model ready")


# ── Routes ────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(req: EmbeddingRequest) -> EmbeddingResponse:
    inputs = [req.input] if isinstance(req.input, str) else req.input
    if not inputs:
        raise HTTPException(status_code=400, detail="input must not be empty")

    try:
        vectors = list(model.embed(inputs))
    except Exception as e:
        logger.exception("Embedding failed")
        raise HTTPException(status_code=500, detail=str(e))

    data = [
        EmbeddingData(
            index=i,
            embedding=v.tolist() if hasattr(v, "tolist") else list(v),
        )
        for i, v in enumerate(vectors)
    ]

    return EmbeddingResponse(
        data=data,
        model=MODEL_NAME,
        usage={"prompt_tokens": sum(len(t.split()) for t in inputs), "total_tokens": sum(len(t.split()) for t in inputs)},
    )


# ── Entrypoint ────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
