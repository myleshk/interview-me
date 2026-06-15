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
    assert "Literal-only" not in prompt  # only with context


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


def test_includes_current_date():
    prompt = build_system_prompt()
    assert f"Today's date is {date.today()}" in prompt


def test_includes_language_constraint():
    prompt = build_system_prompt()
    assert "English" in prompt
    assert "non-English" in prompt
