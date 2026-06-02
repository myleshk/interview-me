"""OpenAI-compatible chat completions endpoint.

Single endpoint — ``POST /v1/chat/completions`` — that accepts the
standard OpenAI chat format, translates it into our LlamaIndex workflow,
and returns streaming SSE chunks or a non-streaming JSON response.

Compatible with LobeChat, ChatGPT-Next-Web, and any OpenAI-compatible
frontend out of the box.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.workflows import AvatarWorkflow
from app.core.rate_limit import rate_limit
from app.core.security import verify_api_key

router = APIRouter(prefix="/v1", tags=["AI"])

# ── OpenAI-compatible schemas ──────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "interview-me"
    messages: list[ChatMessage]
    stream: bool = False

    model_config = {"extra": "ignore"}  # silently drop temperature, max_tokens, etc.


# ── Helpers ───────────────────────────────────────────────


def _get_workflow(request: Request) -> AvatarWorkflow:
    return request.app.state.workflow


def _strip_frontend_system_prompts(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Remove any frontend-injected system messages.
    Our identity prompt is injected server-side inside the workflow —
    we never let the client define the system prompt.
    """
    return [m for m in messages if m.role in ("user", "assistant")]


def _extract_query(messages: list[ChatMessage]) -> str:
    """Extract the last user message as the workflow query."""
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""  # shouldn't happen with normal clients


def _make_sse_chunk(
    chunk_id: str,
    model: str,
    created: int,
    content: str | None,
    *,
    role: str | None = None,
    finish_reason: str | None = None,
) -> str:
    """Render one OpenAI-format SSE chunk as a JSON line."""
    delta: dict[str, Any] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content

    payload: dict[str, Any] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── POST /v1/chat/completions ─────────────────────────────


@router.post(
    "/chat/completions",
    dependencies=[Depends(verify_api_key), Depends(rate_limit)],
    summary="OpenAI-compatible chat completions",
)
async def chat_completions(
    body: ChatRequest,
    request: Request,
):
    """Handle both streaming (SSE) and non-streaming (JSON) responses
    in the standard OpenAI chat completions format."""
    sanitized = _strip_frontend_system_prompts(body.messages)
    query = _extract_query(sanitized)

    workflow = _get_workflow(request)
    token_stream = await workflow.run(query=query)

    if body.stream:
        return _streaming_response(token_stream, model=body.model)
    else:
        return await _non_streaming_response(token_stream, model=body.model)


async def _streaming_response(
    token_stream: AsyncGenerator[str, None],
    *,
    model: str,
) -> StreamingResponse:
    """Yield OpenAI-format SSE chunks."""
    chunk_id = f"chatcmpl-{id(token_stream):x}"
    created = int(time.time())
    first = True

    async def _sse() -> AsyncGenerator[str, None]:
        nonlocal first
        async for token in token_stream:
            if first:
                yield _make_sse_chunk(chunk_id, model, created, token, role="assistant")
                first = False
            else:
                yield _make_sse_chunk(chunk_id, model, created, token)
        yield _make_sse_chunk(chunk_id, model, created, None, finish_reason="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _non_streaming_response(
    token_stream: AsyncGenerator[str, None],
    *,
    model: str,
) -> dict[str, Any]:
    """Collect all tokens and return a single JSON response."""
    chunks: list[str] = []
    async for token in token_stream:
        chunks.append(token)

    return {
        "id": f"chatcmpl-{id(token_stream):x}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,  # echo the requested model so the frontend validates it
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "".join(chunks),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(chunks),
            "total_tokens": 0,
        },
    }
