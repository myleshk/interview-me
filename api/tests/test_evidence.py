"""Tests for deterministic evidence labels and retrieve handoff."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from workflows.events import StartEvent

from app.ai.evidence import build_evidence_packet, classify_scope


def test_scope_labels_follow_filename_and_heading_chain():
    assert classify_scope("1_identity_core.md", "/HIGHLIGHTS", ("HIGHLIGHTS",)) == "inventory"
    assert classify_scope("1_identity_core.md", "/LANGUAGES", ("LANGUAGES",)) == "unscoped"
    assert (
        classify_scope(
            "5_engineering_mind.md",
            "/Technical War Story & Problem Solving",
            ("Technical War Story & Problem Solving",),
        )
        == "narrative"
    )
    assert (
        classify_scope(
            "2_cv_experience.md",
            "/PROJECTS/Software Engineer (backend) Apr 2024 – Present",
            ("Software Engineer (backend) Apr 2024 – Present",),
        )
        == "role"
    )
    assert (
        classify_scope(
            "2_cv_experience.md",
            "/PROJECTS/Full-stack developer May 2020 – Nov 2021/CRM Platform",
            ("CRM Platform",),
        )
        == "project"
    )
    assert classify_scope("2_cv_experience.md", "/CRM Platform", ("CRM Platform",)) == "unscoped"
    assert classify_scope("4_logistics_culture.md", "/Open Source & Side Projects", ()) == "unscoped"


def test_packet_keeps_metadata_and_sets_flags():
    packet = build_evidence_packet(
        [
            {
                "source": "1_identity_core.md",
                "text": "Backend: Spring Boot",
                "document_metadata": {
                    "content_type": "profile",
                    "domains": ["skills"],
                    "sensitivity": "standard",
                },
                "section_path": "/HIGHLIGHTS",
                "section_headings": ["HIGHLIGHTS"],
            },
            {
                "source": "2_cv_experience.md",
                "text": "Membership app backend.",
                "document_metadata": {
                    "content_type": "career_timeline",
                    "domains": ["experience", "projects"],
                    "sensitivity": "standard",
                },
                "section_path": "/PROJECTS/Software Engineer (backend) Apr 2024 – Present",
                "section_headings": ["Software Engineer (backend) Apr 2024 – Present"],
            },
            {
                "source": "2_cv_experience.md",
                "text": "CRM platform work.",
                "document_metadata": {
                    "content_type": "career_timeline",
                    "domains": ["projects"],
                    "sensitivity": "standard",
                },
                "section_path": "/PROJECTS/Full-stack developer May 2020 – Nov 2021/CRM Platform",
                "section_headings": ["CRM Platform"],
            },
            {"source": "ignored.md", "text": "   "},
        ],
        filtered_domains=("skills", "projects"),
        filter_fallback=False,
    )

    assert [item.scope for item in packet.items] == ["inventory", "role", "project"]
    assert packet.items[0].domains == ("skills",)
    assert packet.items[0].section_path == "/HIGHLIGHTS"
    assert packet.items[1].content_type == "career_timeline"
    assert packet.mixed_scopes is True
    assert packet.multi_project is True
    assert packet.sensitive is False
    assert packet.retrieval_empty is False
    assert packet.filtered_domains == ("skills", "projects")
    assert packet.filter_fallback is False


def test_personal_chunk_marks_packet_sensitive():
    packet = build_evidence_packet(
        [
            {
                "source": "6_compensation.md",
                "text": "Compensation notes.",
                "document_metadata": {"sensitivity": "personal", "domains": ["compensation"]},
                "section_path": "/Compensation and Salary",
                "section_headings": ["Compensation and Salary"],
            }
        ]
    )

    assert packet.sensitive is True
    assert packet.items[0].sensitivity == "personal"
    assert packet.items[0].scope == "unscoped"


@pytest.mark.anyio
async def test_retrieve_passes_labeled_evidence_and_logs_flags_only(monkeypatch, caplog):
    from app.ai.qdrant import SearchResponse
    from app.ai.workflows import AvatarWorkflow

    payload = {
        "source": "2_cv_experience.md",
        "text": "Secret chunk body that must stay out of info logs.",
        "document_metadata": {
            "content_type": "career_timeline",
            "domains": ["experience"],
            "sensitivity": "standard",
        },
        "section_path": "/PROJECTS/Software Engineer (backend) Apr 2024 – Present",
        "section_headings": ["Software Engineer (backend) Apr 2024 – Present"],
    }
    workflow = AvatarWorkflow()
    monkeypatch.setattr(workflow, "_embed_query", AsyncMock(return_value=[0.1]))
    monkeypatch.setattr(
        "app.ai.workflows.hybrid_search",
        AsyncMock(
            return_value=SearchResponse(
                payloads=[payload],
                filtered_domains=("experience",),
                filter_fallback=False,
            )
        ),
    )

    with caplog.at_level(logging.INFO):
        event = await workflow.retrieve(None, StartEvent(query="Tell me about your experience"))

    assert event.query == "Tell me about your experience"
    assert event.evidence.items[0].source == "2_cv_experience.md"
    assert event.evidence.items[0].scope == "role"
    assert event.evidence.items[0].domains == ("experience",)
    assert event.evidence.items[0].section_path.endswith("Apr 2024 – Present")
    info_text = "\n".join(record.message for record in caplog.records if record.levelno == logging.INFO)
    assert "mixed_scopes=False" in info_text
    assert "chunks=1" in info_text
    assert "filter_fallback=False" in info_text
    assert "Secret chunk body" not in info_text


@pytest.mark.anyio
async def test_retrieve_failure_returns_empty_packet(monkeypatch):
    from app.ai.workflows import AvatarWorkflow

    workflow = AvatarWorkflow()
    monkeypatch.setattr(workflow, "_embed_query", AsyncMock(side_effect=RuntimeError("down")))

    event = await workflow.retrieve(None, StartEvent(query="hello"))

    assert event.evidence.retrieval_empty is True
    assert event.evidence.items == ()


@pytest.mark.anyio
async def test_synthesize_makes_one_stream_call(monkeypatch):
    from app.ai.workflows import AvatarWorkflow, RetrievedEvent

    class _Delta:
        content = "Hello"

    class _Chunk:
        choices = [SimpleNamespace(delta=_Delta())]

    async def _tokens():
        yield _Chunk()

    create = AsyncMock(return_value=_tokens())
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    workflow = AvatarWorkflow()
    monkeypatch.setattr(workflow, "_get_llm_client", lambda: client)
    packet = build_evidence_packet(
        [
            {
                "source": "2_cv_experience.md",
                "text": "Membership app used Spring Boot.",
                "document_metadata": {"domains": ["experience"], "sensitivity": "standard"},
                "section_path": "/PROJECTS/Software Engineer (backend) Apr 2024 – Present",
                "section_headings": ["Software Engineer (backend) Apr 2024 – Present"],
            }
        ]
    )

    result = await workflow.synthesize(
        None,
        RetrievedEvent(query="Where did you use Spring Boot?", evidence=packet),
    )
    tokens = [token async for token in result.result]

    assert tokens == ["Hello"]
    assert create.await_count == 1
    kwargs = create.await_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["temperature"] == 0.3
    assert len(kwargs["messages"]) == 2
    assert kwargs["messages"][0]["role"] == "system"
    assert "scope=role" in kwargs["messages"][0]["content"]
    assert kwargs["messages"][1] == {
        "role": "user",
        "content": "Where did you use Spring Boot?",
    }
