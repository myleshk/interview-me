"""Tests for metadata-aware retrieval classification and filtering."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.retrieval import classify_query


def test_classifies_explicit_domains():
    result = classify_query("What projects have you built and what tech stack did you use?")

    assert result.domains == ("skills", "projects")
    assert result.matched_terms["skills"] == ("tech stack",)
    assert "built" in result.matched_terms["projects"]


def test_classifies_compensation_without_matching_substrings():
    assert classify_query("What are your salary expectations?").domains == ("compensation",)
    assert classify_query("Tell me about the company").domains == ()


def test_leaves_ambiguous_query_unfiltered():
    assert classify_query("Can you tell me more?").domains == ()


@pytest.mark.anyio
async def test_hybrid_search_applies_domain_filter(monkeypatch):
    from app.ai import qdrant

    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[SimpleNamespace(payload={"source": "experience.md"})]
            )
        )
    )
    monkeypatch.setattr(qdrant, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(qdrant, "ensure_collection", AsyncMock())

    response = await qdrant.hybrid_search([0.1], domains=["experience"])

    assert response.payloads == [{"source": "experience.md"}]
    assert response.filtered_domains == ("experience",)
    assert response.filter_fallback is False
    query_filter = client.query_points.await_args.kwargs["query_filter"]
    assert query_filter.must[0].key == "document_metadata.domains"
    assert query_filter.must[0].match.any == ["experience"]


@pytest.mark.anyio
async def test_hybrid_search_falls_back_when_filter_has_no_results(monkeypatch):
    from app.ai import qdrant

    client = SimpleNamespace(
        query_points=AsyncMock(
            side_effect=[
                SimpleNamespace(points=[]),
                SimpleNamespace(points=[SimpleNamespace(payload={"source": "fallback.md"})]),
            ]
        )
    )
    monkeypatch.setattr(qdrant, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(qdrant, "ensure_collection", AsyncMock())

    response = await qdrant.hybrid_search([0.1], domains=["education"])

    assert response.payloads == [{"source": "fallback.md"}]
    assert response.filter_fallback is True
    assert client.query_points.await_count == 2
    assert client.query_points.await_args_list[0].kwargs["query_filter"] is not None
    assert client.query_points.await_args_list[1].kwargs["query_filter"] is None


@pytest.mark.anyio
async def test_debug_retrieve_exposes_classification_and_metadata(monkeypatch):
    from app.ai import qdrant
    from app.ai.qdrant import SearchResponse
    from app.api import routes_admin

    embedding_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": [{"embedding": [0.1]}]},
    )
    monkeypatch.setattr(routes_admin.httpx, "post", lambda *args, **kwargs: embedding_response)
    search = AsyncMock(
        return_value=SearchResponse(
            payloads=[
                {
                    "source": "experience.md",
                    "text": "Backend experience",
                    "document_metadata": {
                        "content_type": "career_timeline",
                        "domains": ["experience"],
                    },
                    "section_path": "/Experience/Backend",
                    "section_headings": ["Backend"],
                }
            ],
            filtered_domains=("experience",),
            filter_fallback=False,
        )
    )
    monkeypatch.setattr(qdrant, "hybrid_search", search)

    response = await routes_admin.debug_retrieve(
        routes_admin.RetrieveDebugRequest(query="Tell me about your experience")
    )

    assert response.classification.domains == ["experience"]
    assert response.classification.filter_fallback is False
    assert response.chunks[0].document_metadata["content_type"] == "career_timeline"
    assert response.chunks[0].section_path == "/Experience/Backend"
    assert search.await_args.kwargs["domains"] == ["experience"]
