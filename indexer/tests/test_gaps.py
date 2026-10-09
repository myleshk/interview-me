"""Tests for the offline gap queue. Fixtures are synthetic."""

import json
from pathlib import Path

import pytest

from gaps import GapError, apply_answer, audit_knowledge, priority, validate_queue


def _write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


def _corpus(root: Path) -> None:
    _write(
        root,
        "1_identity_core.md",
        "\n".join(
            [
                "# HIGHLIGHTS",
                "",
                "* Backend: Spring Boot, Django",
                "* Frontend: React Native, React",
                "* Languages: Java, JavaScript",
                "* Tools & Methodologies: Jira, Agile",
                "",
            ]
        ),
    )
    _write(
        root,
        "2_cv_experience.md",
        "\n".join(
            [
                "# PROJECTS",
                "",
                "## Backend Engineer Jan 2024 – Present",
                "",
                "Membership App, Example Corp, City",
                "",
                "* **Tech Stack:** Java, Spring Boot, React Native",
                "",
                "## Other Engineer Jan 2020 – Jan 2022",
                "",
                "Other App, Other Corp, City",
                "",
                "* **Tech Stack:** JavaScript, Java",
                "* **Tech Stack:** remains on the role",
                "",
                "### Unscoped Product",
                "",
                "Built features without repeating the stack.",
                "",
                "### Scoped Product",
                "",
                "* **Tech Stack:** Java",
                "",
            ]
        ),
    )
    _write(
        root,
        "4_logistics_culture.md",
        "\n".join(
            [
                "### Open Source & Side Projects",
                "",
                "* **Widget:** shipped in 2019.",
                "* **Gadget:** built a small tool.",
                "* https://tools.example.com: a bookmark tool.",
                "",
                "### Personal Life & Hobbies",
                "",
                "* **Family:** not an audit target.",
                "",
            ]
        ),
    )
    _write(
        root,
        "5_engineering_mind.md",
        "\n".join(
            [
                "# Profile",
                "",
                "## Core Engineering Philosophy",
                "",
                "Prefer clear code.",
                "",
                "## Technical War Story",
                "",
                "* **The Challenge**: an unnamed microservice failed.",
                "* **The Outcome**: it was repaired.",
                "",
            ]
        ),
    )
    _write(
        root,
        "6_compensation.md",
        "# Compensation\n\nPrivate figures stay out of the audit.\n",
    )


def _keys(document: dict) -> dict[str, dict]:
    return {gap["dedupe_key"]: gap for gap in document["gaps"]}


def test_detectors_follow_scope_rules(tmp_path: Path):
    _corpus(tmp_path)

    document = audit_knowledge(tmp_path)
    found = _keys(document)

    spring = found["1_identity_core.md|/HIGHLIGHTS|where_used:Spring Boot"]
    assert spring["kind"] == "incomplete"
    assert spring["subject"]["employer"] == "Example Corp"
    assert "only place" in spring["question"]

    django = found["1_identity_core.md|/HIGHLIGHTS|where_used:Django"]
    assert django["kind"] == "unknown"
    assert "not in any role" in django["question"]

    react = found["1_identity_core.md|/HIGHLIGHTS|where_used:React"]
    assert react["kind"] == "unknown"
    native = found["1_identity_core.md|/HIGHLIGHTS|where_used:React Native"]
    assert native["kind"] == "incomplete"

    assert "1_identity_core.md|/HIGHLIGHTS|where_used:Java" not in found
    assert "1_identity_core.md|/HIGHLIGHTS|where_used:JavaScript" in found
    assert all("Jira" not in key and "Agile" not in key for key in found)

    stack_keys = [key for key in found if key.endswith("|missing_stack")]
    assert len(stack_keys) == 1
    assert stack_keys[0].endswith("Unscoped Product|missing_stack")

    episode_keys = [key for key in found if key.endswith("|episode_scope")]
    assert len(episode_keys) == 1
    assert all("Philosophy" not in key for key in episode_keys)

    side_keys = [key for key in found if "side_project_year:" in key]
    assert side_keys == [
        "4_logistics_culture.md|/Open Source & Side Projects|side_project_year:Gadget",
        "4_logistics_culture.md|/Open Source & Side Projects|side_project_year:https://tools.example.com",
    ]
    assert all("Family" not in key for key in found)
    assert all(gap["subject"]["source"] != "6_compensation.md" for gap in document["gaps"])


def test_bound_episode_is_not_a_gap(tmp_path: Path):
    _corpus(tmp_path)
    text = (tmp_path / "5_engineering_mind.md").read_text(encoding="utf-8")
    text = text.replace(
        "an unnamed microservice failed.",
        "the Membership App microservice at Example Corp failed.",
    )
    (tmp_path / "5_engineering_mind.md").write_text(text, encoding="utf-8")

    found = _keys(audit_knowledge(tmp_path))

    assert not any(key.endswith("|episode_scope") for key in found)


def test_rerun_keeps_ids_and_suppresses_closed_gaps(tmp_path: Path):
    _corpus(tmp_path)
    first = audit_knowledge(tmp_path)
    second = audit_knowledge(tmp_path, first)

    assert [(gap["id"], gap["dedupe_key"]) for gap in first["gaps"]] == [
        (gap["id"], gap["dedupe_key"]) for gap in second["gaps"]
    ]

    closed = first["gaps"][0]
    closed["status"] = "dismissed"
    merged = audit_knowledge(tmp_path, first)
    matches = [gap for gap in merged["gaps"] if gap["dedupe_key"] == closed["dedupe_key"]]
    assert len(matches) == 1
    assert matches[0]["status"] == "dismissed"

    closed["status"] = "resolved"
    merged = audit_knowledge(tmp_path, first)
    matches = [gap for gap in merged["gaps"] if gap["dedupe_key"] == closed["dedupe_key"]]
    assert len(matches) == 1
    assert matches[0]["status"] == "resolved"


def test_filled_gap_becomes_stale_instead_of_duplicating(tmp_path: Path):
    _corpus(tmp_path)
    first = audit_knowledge(tmp_path)
    django_key = "1_identity_core.md|/HIGHLIGHTS|where_used:Django"
    original = next(gap for gap in first["gaps"] if gap["dedupe_key"] == django_key)

    highlights = (tmp_path / "1_identity_core.md").read_text(encoding="utf-8")
    (tmp_path / "1_identity_core.md").write_text(
        highlights.replace("Spring Boot, Django", "Spring Boot"),
        encoding="utf-8",
    )
    second = audit_knowledge(tmp_path, first)
    matches = [gap for gap in second["gaps"] if gap["dedupe_key"] == django_key]

    assert len(matches) == 1
    assert matches[0]["id"] == original["id"]
    assert matches[0]["status"] == "stale"


def test_conflicting_answer_keeps_both_wordings():
    gap = {
        "kind": "incomplete",
        "status": "open",
        "answer": None,
        "resolution": None,
    }

    apply_answer(gap, "I owned it.", "Owned the service.", "2026-10-10")
    apply_answer(gap, "I maintained it.", "Maintained the service.", "2026-10-10")

    assert gap["kind"] == "conflicting"
    assert gap["status"] == "answered"
    assert gap["resolution"]["proposed_edit"] == "Maintained the service."
    assert gap["resolution"]["prior_proposed_edits"] == ["Owned the service."]
    assert gap["resolution"]["provenance"] == "owner_direct"


def test_ownership_priority_outranks_side_project(tmp_path: Path):
    _corpus(tmp_path)
    document = audit_knowledge(tmp_path)
    side = next(gap for gap in document["gaps"] if "side_project_year:" in gap["dedupe_key"])
    ownership = priority(3, 3, 3, 1)

    assert ownership["score"] > side["priority"]["score"]
    assert document["gaps"][0]["priority"]["score"] >= document["gaps"][-1]["priority"]["score"]


def test_loader_rejects_missing_paths_duplicates_and_bad_scores(tmp_path: Path):
    _corpus(tmp_path)
    document = audit_knowledge(tmp_path)
    document["gaps"][0]["subject"]["source"] = "missing.md"
    with pytest.raises(GapError, match="missing source file"):
        validate_queue(document, tmp_path)

    document = audit_knowledge(tmp_path)
    document["gaps"].append(dict(document["gaps"][0]))
    with pytest.raises(GapError, match="duplicate"):
        validate_queue(document, tmp_path)

    document = audit_knowledge(tmp_path)
    document["gaps"][0]["priority"]["score"] = 0
    with pytest.raises(GapError, match="priority.score"):
        validate_queue(document, tmp_path)

    document = audit_knowledge(tmp_path)
    document["gaps"][0]["kind"] = "guess"
    with pytest.raises(GapError, match="invalid kind"):
        validate_queue(document, tmp_path)


def test_queue_round_trip_json(tmp_path: Path):
    _corpus(tmp_path)
    document = audit_knowledge(tmp_path)
    path = tmp_path / "learning" / "gaps.json"
    path.parent.mkdir()
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    validate_queue(loaded, tmp_path)
    assert loaded["schema_version"] == 1
