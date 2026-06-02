"""LlamaIndex Workflow — async event-driven RAG pipeline.

Architecture::

    StartEvent → [retrieve] → RetrievedEvent → [synthesize] → StopEvent

- **retrieve**  — Queries Qdrant hybrid search (or returns mock chunks).
- **synthesize** — Streams a response from DeepSeek with identity-grounded
  system prompt + retrieved context.

The workflow returns an ``AsyncGenerator[str, None]`` suitable for SSE.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from workflows import Context, Workflow, step
from workflows.events import Event, StartEvent, StopEvent

from app.core.config import settings
from app.ai.prompts import build_system_prompt

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
        1. ``retrieve``   — pull relevant context from Qdrant (mock for now).
        2. ``synthesize`` — stream a response from DeepSeek with
           identity-grounded system prompt + context.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._llm_client: AsyncOpenAI | None = None

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

    # ── Step 1: Retrieve ─────────────────────────────────────

    @step
    async def retrieve(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> RetrievedEvent:
        """Retrieve relevant context for the query.

        Currently returns mock chunks. Wire up
        ``app.ai.qdrant.hybrid_search()`` when Qdrant is populated.
        """
        query: str = ev.get("query", "")

        # TODO: Replace with real Qdrant hybrid search
        # from app.ai.qdrant import hybrid_search
        # results = await hybrid_search(query_vector=..., limit=5)
        # context_chunks = [r["text"] for r in results]

        mock_chunks: list[str] = [
            f"[MOCK] Retrieved context for query: '{query}'",
            "[MOCK] Myles Fang is a Senior Backend Software Engineer at Melco Resorts, Hong Kong.",
            "[MOCK] Core stack: Java Spring Boot, Go (Gin/Echo), MySQL, Next.js, React Native.",
            "[MOCK] Active projects: hk-independent-bus-eta, transfer-hk, Dify interview bot.",
        ]

        logger.info("retrieve | query=%s  chunks=%d", query, len(mock_chunks))
        return RetrievedEvent(query=query, context_chunks=mock_chunks)

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
