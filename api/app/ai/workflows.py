"""LlamaIndex Workflow — async event-driven RAG pipeline.

Architecture::

    StartEvent → [retrieve] → RetrievedEvent → [synthesize] → StopEvent

- **retrieve**  — Embeds the user query, searches Qdrant, labels each hit.
- **synthesize** — Streams one DeepSeek response from the identity prompt
  plus that labeled evidence.

The workflow returns an ``AsyncGenerator[str, None]`` suitable for SSE.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from workflows import Context, Workflow, step
from workflows.events import Event, StartEvent, StopEvent

from app.core.config import settings
from app.ai.evidence import EvidencePacket, build_evidence_packet
from app.ai.prompts import build_system_prompt
from app.ai.qdrant import hybrid_search
from app.ai.retrieval import classify_query

logger = logging.getLogger(__name__)


# ── Custom Events ──────────────────────────────────────────


class RetrievedEvent(Event):
    """Carries the labeled evidence packet to the synthesize step."""

    query: str
    evidence: EvidencePacket


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
        self._http: httpx.AsyncClient | None = None

    # ── Lazy HTTP client ───────────────────────────────────

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._http

    # ── Lazy LLM client ────────────────────────────────────

    def _get_llm_client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client (NOT a @property — avoids eager
        evaluation during ``inspect.getmembers`` inside workflow validation)."""
        if self._llm_client is None:
            import httpx as _httpx

            self._llm_client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                timeout=_httpx.Timeout(60.0, connect=10.0),
                max_retries=1,
            )
        return self._llm_client

    # ── Embedding (remote service) ─────────────────────────

    async def _embed_query(self, query: str) -> list[float]:
        """Embed a query string via the remote embedding service."""
        resp = await self._get_http().post(
            f"{settings.embedding_service_url}/v1/embeddings",
            json={"input": query},
        )
        resp.raise_for_status()
        body = resp.json()
        return list(body["data"][0]["embedding"])

    # ── Step 1: Retrieve ─────────────────────────────────────

    @step
    async def retrieve(
        self,
        ctx: Context,
        ev: StartEvent,
    ) -> RetrievedEvent:
        """Embed the query, search Qdrant, and label the hits.

        Falls back to an empty evidence packet when Qdrant is unreachable
        or contains no indexed data. The identity in the system prompt
        remains the abstention baseline.
        """
        query: str = ev.get("query", "")
        results: list[dict[str, Any]] = []
        filtered_domains: tuple[str, ...] = ()
        filter_fallback = False

        try:
            query_vector = await self._embed_query(query)

            classification = classify_query(query)
            search = await hybrid_search(
                query_vector=query_vector,
                limit=8,
                domains=list(classification.domains),
            )
            results = search.payloads
            filtered_domains = tuple(search.filtered_domains)
            filter_fallback = search.filter_fallback
        except Exception:
            logger.exception("retrieve | Qdrant search failed — returning empty context")

        evidence = build_evidence_packet(
            results,
            filtered_domains=filtered_domains,
            filter_fallback=filter_fallback,
        )
        logger.info(
            "retrieve | domains=%s mixed_scopes=%s multi_project=%s sensitive=%s "
            "chunks=%d filter_fallback=%s retrieval_empty=%s",
            list(evidence.filtered_domains),
            evidence.mixed_scopes,
            evidence.multi_project,
            evidence.sensitive,
            len(evidence.items),
            evidence.filter_fallback,
            evidence.retrieval_empty,
        )
        for item in evidence.items:
            preview = item.text[:300] + "…" if len(item.text) > 300 else item.text
            logger.debug(
                "retrieve | source=%s scope=%s section=%s text=%s",
                item.source,
                item.scope,
                item.section_path,
                preview,
            )

        return RetrievedEvent(query=query, evidence=evidence)

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
        system_prompt = build_system_prompt(evidence=ev.evidence)
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
                    max_tokens=1000,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
            except Exception:
                logger.exception("synthesize | streaming error")
                yield "[Error: failed to generate response]"

        logger.debug(
            "synthesize | query=%s  chunks=%d",
            ev.query,
            len(ev.evidence.items),
        )
        return StopEvent(result=_stream_tokens())
