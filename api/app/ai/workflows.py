"""LlamaIndex Workflow — async event-driven RAG pipeline.

Architecture::

    StartEvent → [retrieve] → RetrievedEvent → [synthesize] → StopEvent

- **retrieve**  — Embeds the user query, searches Qdrant with dense vectors.
- **synthesize** — Streams a response from DeepSeek with identity-grounded
  system prompt + retrieved context.

The workflow returns an ``AsyncGenerator[str, None]`` suitable for SSE.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastembed import TextEmbedding
from openai import AsyncOpenAI
from workflows import Context, Workflow, step
from workflows.events import Event, StartEvent, StopEvent

from app.core.config import settings
from app.ai.prompts import build_system_prompt
from app.ai.qdrant import hybrid_search

logger = logging.getLogger(__name__)


# ── Custom Events ──────────────────────────────────────────


class RetrievedEvent(Event):
    """Carries retrieved context chunks to the synthesize step."""

    query: str
    context_chunks: list[str]


# ── Workflow ───────────────────────────────────────────────


class AvatarWorkflow(Workflow):
    """Event-driven RAG workflow backed by LlamaIndex Workflows.

    Steps:
        1. ``retrieve``   — embed query, search Qdrant, return chunks.
        2. ``synthesize`` — stream a response from DeepSeek with
           identity-grounded system prompt + context.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._llm_client: AsyncOpenAI | None = None
        self._embed_model: TextEmbedding | None = None

    # ── Lazy LLM client ────────────────────────────────────

    def _get_llm_client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client (NOT a @property — avoids eager
        evaluation during ``inspect.getmembers`` inside workflow validation)."""
        if self._llm_client is None:
            self._llm_client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._llm_client

    # ── Lazy embedding model ───────────────────────────────

    def _get_embed_model(self) -> TextEmbedding:
        """Lazy-init the FastEmbed model (local, no API call)."""
        if self._embed_model is None:
            self._embed_model = TextEmbedding(
                model_name=settings.embedding_model_name
            )
        return self._embed_model

    # ── Step 1: Retrieve ─────────────────────────────────────

    @step
    async def retrieve(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> RetrievedEvent:
        """Embed the query, search Qdrant, return relevant chunks.

        Falls back to an empty context list when Qdrant is unreachable
        or contains no indexed data — the identity in the system prompt
        remains available as the anti-hallucination baseline.
        """
        query: str = ev.get("query", "")

        try:
            model = self._get_embed_model()
            query_vectors = list(model.embed([query]))
            query_vector = query_vectors[0].tolist() if hasattr(query_vectors[0], "tolist") else query_vectors[0]

            results = await hybrid_search(
                query_vector=list(query_vector),
                limit=5,
            )
        except Exception:
            logger.exception("retrieve | Qdrant search failed — returning empty context")
            results = []

        context_chunks = [r.get("text", "") for r in results if r.get("text")]

        logger.info(
            "retrieve | query=%s  results=%d  chunks=%d",
            query,
            len(results),
            len(context_chunks),
        )
        for i, chunk in enumerate(context_chunks):
            preview = chunk[:300] + "…" if len(chunk) > 300 else chunk
            source = results[i].get("source", "?") if i < len(results) else "?"
            logger.debug("retrieve | chunk[%d] source=%s  text=%s", i, source, preview)

        return RetrievedEvent(query=query, context_chunks=context_chunks)

    # ── Step 2: Synthesize ───────────────────────────────────

    @step
    async def synthesize(
        self,
        ctx: Context,
        ev: RetrievedEvent,
    ) -> StopEvent:
        """Call DeepSeek with identity-grounded system prompt + context.

        Returns a ``StopEvent`` whose ``result`` is an async generator
        yielding response tokens for SSE streaming.
        """
        system_prompt = build_system_prompt(context_chunks=ev.context_chunks)
        logger.debug("synthesize | system_prompt (%d chars):\n%s", len(system_prompt), system_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": ev.query},
        ]

        # Capture the client reference *before* the async closure so
        # we avoid `self.llm_client` property evaluation at runtime.
        llm_client = self._get_llm_client()

        async def _stream_tokens() -> AsyncGenerator[str, None]:
            try:
                stream = await llm_client.chat.completions.create(
                    model=settings.deepseek_model,
                    messages=messages,  # type: ignore[arg-type]
                    stream=True,
                    temperature=0.3,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
            except Exception:
                logger.exception("synthesize | streaming error")
                yield "[Error: failed to generate response]"

        logger.info(
            "synthesize | query=%s  context_chunks=%d",
            ev.query,
            len(ev.context_chunks),
        )
        return StopEvent(result=_stream_tokens())
