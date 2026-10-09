"""Tests for system prompt builder.

NOTE: String assertions below are canary checks — they verify key phrases
appear/disappear as expected. If prompt wording changes, these may need
updating, but that's intentional: they catch accidental prompt regressions.
"""

from datetime import date

from app.ai.prompts import build_system_prompt


def test_includes_identity_fields():
    prompt = build_system_prompt()
    assert "Test User" in prompt
    assert "Test Engineer" in prompt
    assert "Test Corp" in prompt
    assert "Test City" in prompt


def test_includes_guardrails():
    prompt = build_system_prompt()
    assert "Never fabricate" in prompt
    assert "According to my knowledge base" in prompt
    assert "first-person limit" in prompt
    assert "Literal-only" not in prompt  # only with context
    assert "CRITICAL — Evidence scope:" not in prompt


def test_context_chunks_injected():
    prompt = build_system_prompt(context_chunks=["Skill: Python", "Skill: Docker"])
    assert "Skill: Python" in prompt
    assert "Skill: Docker" in prompt
    assert "Literal-only" in prompt  # guardrail appears with context
    assert "--- Your Knowledge ---" in prompt


def test_no_context_fallback():
    prompt = build_system_prompt(context_chunks=[])
    assert "no additional knowledge loaded" in prompt
    assert "You have no additional knowledge loaded" in prompt
    assert "don't recall" in prompt


def test_labeled_evidence_keeps_scope_rules_and_meta_ban():
    from app.ai.evidence import build_evidence_packet

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
                "text": "Membership app used Java and Spring Boot.",
                "document_metadata": {
                    "content_type": "career_timeline",
                    "domains": ["experience", "projects"],
                    "sensitivity": "standard",
                },
                "section_path": "/PROJECTS/Software Engineer (backend) Apr 2024 – Present",
                "section_headings": ["Software Engineer (backend) Apr 2024 – Present"],
            },
        ]
    )

    prompt = build_system_prompt(evidence=packet)

    assert "scope=inventory" in prompt
    assert "scope=role" in prompt
    assert "source=1_identity_core.md" in prompt
    assert "section=/HIGHLIGHTS" in prompt
    assert "CRITICAL — Evidence scope:" in prompt
    assert "first-person limit" in prompt
    assert "According to my knowledge base" in prompt
    assert "Do not mention a knowledge base" in prompt
    assert "mixed_scopes=true" in prompt
    assert "Literal-only" in prompt


def test_empty_evidence_packet_uses_identity_fallback():
    from app.ai.evidence import build_evidence_packet

    prompt = build_system_prompt(evidence=build_evidence_packet([]))

    assert "no additional knowledge loaded" in prompt
    assert "don't recall" in prompt
    assert "CRITICAL — Evidence scope:" not in prompt


def test_personal_sensitivity_is_labeled():
    from app.ai.evidence import build_evidence_packet

    packet = build_evidence_packet(
        [
            {
                "source": "6_compensation.md",
                "text": "Compensation notes.",
                "document_metadata": {
                    "content_type": "compensation_preferences",
                    "domains": ["compensation"],
                    "sensitivity": "personal",
                },
                "section_path": "/Compensation and Salary",
                "section_headings": ["Compensation and Salary"],
            }
        ]
    )

    prompt = build_system_prompt(evidence=packet)

    assert "sensitivity=personal" in prompt
    assert "sensitive=true" in prompt


def test_includes_current_date():
    prompt = build_system_prompt()
    assert f"Today's date is {date.today()}" in prompt


def test_includes_language_constraint():
    prompt = build_system_prompt()
    assert "English" in prompt
    assert "non-English" in prompt
