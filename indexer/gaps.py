"""Offline knowledge-gap queue.

The audit reads Markdown in the knowledge directory and writes
``data/learning/gaps.json``. It does not embed text or talk to Qdrant.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

KINDS = {"incomplete", "ambiguous", "conflicting", "unknown"}
STATUSES = {
    "open",
    "dismissed",
    "answered",
    "approved_pending_index",
    "resolved",
    "rejected",
    "stale",
}
PRESERVED_STATUSES = {
    "dismissed",
    "resolved",
    "rejected",
    "answered",
    "approved_pending_index",
}
CREATED_FROM = {"audit", "owner_requested"}

_HIGHLIGHTS_FILE = "1_identity_core.md"
_EXPERIENCE_FILE = "2_cv_experience.md"
_LOGISTICS_FILE = "4_logistics_culture.md"
_NARRATIVE_FILE = "5_engineering_mind.md"

_INCLUDED_CATEGORIES = {
    "frontend",
    "backend",
    "databases & messaging",
    "testing",
    "languages",
    "devops & cloud",
}
_SKIPPED_TOOLS = {
    "opensearch",
    "swagger",
    "kibana",
    "jira",
    "servicenow",
    "countly",
    "google analytics",
    "figma",
    "asana",
    "agile",
    "scrum",
}
_NARRATIVE_SKIP = (
    "philosophy",
    "leadership",
    "team dynamics",
    "strategic vision",
    "future role",
    "career goal",
)
_EPISODE_HINTS = ("war story", "the challenge", "the outcome", "microservice")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$", re.MULTILINE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_TECH_STACK = re.compile(r"tech stack", re.IGNORECASE)
_LEGAL_SUFFIX = re.compile(r"\s+(?:Ltd\.?|Limited|Co\.?|Inc\.?|LLC)$", re.IGNORECASE)


class GapError(ValueError):
    """Raised when a gap queue or knowledge section is invalid."""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def priority(impact: int, interview_weight: int, risk: int, effort: int) -> dict[str, int]:
    return {
        "impact": impact,
        "interview_weight": interview_weight,
        "misrepresentation_risk": risk,
        "effort": effort,
        "score": impact + interview_weight + risk - effort,
    }


def _clean_heading(raw: str) -> str:
    cleaned = raw.strip().strip("*").strip()
    return re.sub(r"\s+", " ", cleaned)


def parse_sections(text: str) -> list[dict[str, Any]]:
    """Split Markdown into heading sections, including nested body text."""
    lines = text.splitlines()
    marks: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match:
            continue
        marks.append((index, len(match.group(1)), _clean_heading(match.group(2))))

    sections: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    for position, (start, level, title) in enumerate(marks):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = len(lines)
        for later in marks[position + 1 :]:
            if later[1] <= level:
                end = later[0]
                break
        body = "\n".join(lines[start + 1 : end]).strip()
        sections.append(
            {
                "level": level,
                "heading": title,
                "body": body,
                "path": "/" + "/".join(item for _, item in stack),
                "start": start,
                "end": end,
            }
        )
    return sections


def _read(data_dir: Path, name: str) -> str | None:
    path = data_dir / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _section_map(text: str) -> dict[str, dict[str, Any]]:
    return {section["path"]: section for section in parse_sections(text)}


def _preamble(text: str, section: dict[str, Any], children: list[dict[str, Any]]) -> str:
    lines = text.splitlines()
    end = section["end"]
    if children:
        end = min(child["start"] for child in children)
    return "\n".join(lines[section["start"] + 1 : end]).strip()


def _role_identity(preamble: str) -> tuple[str | None, str | None]:
    """Return ``(employer, project)`` from the first 'Product, Employer, Place' line."""
    for line in preamble.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("*", "-", "#")):
            continue
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        if len(parts) >= 2:
            return parts[1], parts[0]
        return None, None
    return None, None


def _soften_org(name: str) -> str:
    return _LEGAL_SUFFIX.sub("", name).strip()


def _roles(text: str) -> list[dict[str, Any]]:
    sections = parse_sections(text)
    roles = [section for section in sections if section["level"] == 2]
    built: list[dict[str, Any]] = []
    for role in roles:
        children = [
            section
            for section in sections
            if section["level"] == 3 and section["path"].startswith(role["path"] + "/")
        ]
        preamble = _preamble(text, role, children)
        employer, project = _role_identity(preamble)
        built.append(
            {
                **role,
                "preamble": preamble,
                "children": children,
                "employer": employer,
                "project": project,
                "hash": sha256_text(f"{role['heading']}\n{role['body']}"),
            }
        )
    return built


def _names_from_roles(roles: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for role in roles:
        for value in (role["employer"], role["project"]):
            if isinstance(value, str) and len(value) >= 4:
                names.append(value)
                softened = _soften_org(value)
                if len(softened) >= 4:
                    names.append(softened)
        for child in role["children"]:
            if len(child["heading"]) >= 4:
                names.append(child["heading"])
    return names


def _highlight_techs(text: str) -> list[tuple[str, str]]:
    """Return ``(category, technology)`` pairs from the highlight inventory."""
    section = next(
        (item for item in parse_sections(text) if item["heading"].casefold() == "highlights"),
        None,
    )
    if section is None:
        return []
    found: list[tuple[str, str]] = []
    for line in section["body"].splitlines():
        match = re.match(r"^\s*[-*]\s+([^:]+):\s*(.+)$", line)
        if not match:
            continue
        category = match.group(1).strip()
        if category.casefold() not in _INCLUDED_CATEGORIES:
            continue
        for part in match.group(2).split(","):
            tech = part.strip().strip("*").strip()
            if not tech or tech.casefold() in _SKIPPED_TOOLS:
                continue
            found.append((category, tech))
    return found


def _find_techs(text: str, techs: list[str]) -> set[str]:
    """Match technology names without treating one name as part of a longer one."""
    masked = text
    found: set[str] = set()
    boundary = r"[\w.+#]"
    for tech in sorted(techs, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<!{boundary}){re.escape(tech)}(?!{boundary})",
            re.IGNORECASE,
        )
        if pattern.search(masked):
            found.add(tech)
            masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return found


def _evidence(source: str, section_path: str, quote: str) -> dict[str, str]:
    return {
        "source": source,
        "section_path": section_path,
        "quote_hash": sha256_text(quote),
    }


def _gap(
    *,
    dedupe_key: str,
    kind: str,
    source: str,
    section_path: str,
    section_hash: str,
    employer: str | None,
    project: str | None,
    attribute: str,
    known_evidence: list[dict[str, str]],
    missing: str,
    question: str,
    scores: dict[str, int],
) -> dict[str, Any]:
    return {
        "id": "",
        "dedupe_key": dedupe_key,
        "kind": kind,
        "status": "open",
        "subject": {
            "source": source,
            "section_path": section_path,
            "section_hash": section_hash,
            "employer": employer,
            "project": project,
        },
        "attribute": attribute,
        "known_evidence": known_evidence,
        "missing": missing,
        "priority": scores,
        "question": question,
        "created_from": "audit",
        "answer": None,
        "resolution": None,
    }


def _highlight_gaps(data_dir: Path) -> dict[str, dict[str, Any]]:
    highlights = _read(data_dir, _HIGHLIGHTS_FILE)
    experience = _read(data_dir, _EXPERIENCE_FILE)
    if highlights is None:
        return {}
    section = next(
        (item for item in parse_sections(highlights) if item["heading"].casefold() == "highlights"),
        None,
    )
    if section is None:
        return {}
    techs = _highlight_techs(highlights)
    names = [tech for _, tech in techs]
    roles = _roles(experience) if experience is not None else []
    located = {tech: [role for role in roles if tech in _find_techs(role["body"], names)] for tech in names}
    section_hash = sha256_text(f"{section['heading']}\n{section['body']}")
    gaps: dict[str, dict[str, Any]] = {}
    for _category, tech in techs:
        matches = located[tech]
        if len(matches) >= 2:
            continue
        attribute = f"where_used:{tech}"
        dedupe_key = f"{_HIGHLIGHTS_FILE}|{section['path']}|{attribute}"
        evidence = [_evidence(_HIGHLIGHTS_FILE, section["path"], section["body"])]
        if len(matches) == 1:
            role = matches[0]
            evidence.append(_evidence(_EXPERIENCE_FILE, role["path"], role["body"]))
            kind = "incomplete"
            scores = priority(3, 3, 2, 1)
            missing = f"Whether {tech} was used only in {role['heading']}."
            question = (
                f"{tech} is on the highlight list and in {role['heading']}. "
                "Was that the only place you used it?"
            )
            employer, project = role["employer"], role["project"]
        else:
            kind = "unknown"
            scores = priority(3, 3, 3, 1)
            missing = f"Where {tech} was used. No role section names it."
            question = (
                f"Where did you use {tech}? It is on the highlight list and not in any role section."
            )
            employer, project = None, None
        gaps[dedupe_key] = _gap(
            dedupe_key=dedupe_key,
            kind=kind,
            source=_HIGHLIGHTS_FILE,
            section_path=section["path"],
            section_hash=section_hash,
            employer=employer,
            project=project,
            attribute=attribute,
            known_evidence=evidence,
            missing=missing,
            question=question,
            scores=scores,
        )
    return gaps


def _stack_gaps(data_dir: Path) -> dict[str, dict[str, Any]]:
    experience = _read(data_dir, _EXPERIENCE_FILE)
    if experience is None:
        return {}
    gaps: dict[str, dict[str, Any]] = {}
    for role in _roles(experience):
        if not _TECH_STACK.search(role["preamble"]):
            continue
        for child in role["children"]:
            if _TECH_STACK.search(child["body"]):
                continue
            attribute = "missing_stack"
            dedupe_key = f"{_EXPERIENCE_FILE}|{child['path']}|{attribute}"
            section_hash = sha256_text(f"{child['heading']}\n{child['body']}")
            gaps[dedupe_key] = _gap(
                dedupe_key=dedupe_key,
                kind="incomplete",
                source=_EXPERIENCE_FILE,
                section_path=child["path"],
                section_hash=section_hash,
                employer=role["employer"],
                project=child["heading"],
                attribute=attribute,
                known_evidence=[
                    _evidence(_EXPERIENCE_FILE, role["path"], role["preamble"]),
                    _evidence(_EXPERIENCE_FILE, child["path"], child["body"]),
                ],
                missing=f"The tech stack for {child['heading']} is not written under that product.",
                question=(
                    f"What technologies did you use on {child['heading']} ({role['heading']})? "
                    "That product section does not list a stack, and the role section does."
                ),
                scores=priority(2, 2, 2, 1),
            )
    return gaps


def _episode_gaps(data_dir: Path) -> dict[str, dict[str, Any]]:
    narrative = _read(data_dir, _NARRATIVE_FILE)
    if narrative is None:
        return {}
    experience = _read(data_dir, _EXPERIENCE_FILE)
    names = _names_from_roles(_roles(experience) if experience is not None else [])
    gaps: dict[str, dict[str, Any]] = {}
    for section in parse_sections(narrative):
        if section["level"] < 2:
            continue
        heading = section["heading"]
        lowered = heading.casefold()
        if any(skip in lowered for skip in _NARRATIVE_SKIP):
            continue
        blob = f"{heading}\n{section['body']}".casefold()
        if not any(hint in blob for hint in _EPISODE_HINTS):
            continue
        if any(name.casefold() in blob for name in names):
            continue
        attribute = "episode_scope"
        dedupe_key = f"{_NARRATIVE_FILE}|{section['path']}|{attribute}"
        gaps[dedupe_key] = _gap(
            dedupe_key=dedupe_key,
            kind="incomplete",
            source=_NARRATIVE_FILE,
            section_path=section["path"],
            section_hash=sha256_text(f"{heading}\n{section['body']}"),
            employer=None,
            project=None,
            attribute=attribute,
            known_evidence=[_evidence(_NARRATIVE_FILE, section["path"], section["body"])],
            missing=f"The employer and product for the episode '{heading}' are not named.",
            question=f"Which employer and product does this episode belong to: {heading}?",
            scores=priority(2, 2, 3, 1),
        )
    return gaps


def _bullet_label(bullet: str) -> str:
    match = re.match(r"\*\*(.+?)\*\*", bullet)
    if match:
        return match.group(1).strip().strip(":")
    url = re.match(r"(https?://\S+)", bullet)
    if url:
        return url.group(1).rstrip(":,.)")
    label = bullet.split(":", 1)[0].strip()
    return label[:80] or bullet[:80]


def _side_project_gaps(data_dir: Path) -> dict[str, dict[str, Any]]:
    logistics = _read(data_dir, _LOGISTICS_FILE)
    if logistics is None:
        return {}
    section = next(
        (
            item
            for item in parse_sections(logistics)
            if "open source" in item["heading"].casefold() and "side project" in item["heading"].casefold()
        ),
        None,
    )
    if section is None:
        return {}
    section_hash = sha256_text(f"{section['heading']}\n{section['body']}")
    gaps: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    for bullet in _BULLET.findall(section["body"]):
        if _YEAR.search(bullet):
            continue
        label = _bullet_label(bullet)
        seen[label] = seen.get(label, 0) + 1
        suffix = label if seen[label] == 1 else f"{label} #{seen[label]}"
        attribute = f"side_project_year:{suffix}"
        dedupe_key = f"{_LOGISTICS_FILE}|{section['path']}|{attribute}"
        gaps[dedupe_key] = _gap(
            dedupe_key=dedupe_key,
            kind="incomplete",
            source=_LOGISTICS_FILE,
            section_path=section["path"],
            section_hash=section_hash,
            employer=None,
            project=label,
            attribute=attribute,
            known_evidence=[_evidence(_LOGISTICS_FILE, section["path"], bullet)],
            missing=f"No year is given for the side project {label}.",
            question=f"What year did you do {label}? The side-project note does not give one.",
            scores=priority(1, 1, 1, 1),
        )
    return gaps


def detect_gaps(data_dir: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for detector in (_highlight_gaps, _stack_gaps, _episode_gaps, _side_project_gaps):
        found.update(detector(data_dir))
    return found


def merge_findings(
    data_dir: Path,
    findings: dict[str, dict[str, Any]],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    """Refresh open gaps, keep closed ones, and mark disappeared sections stale."""
    previous = list(existing["gaps"]) if existing else []
    by_key = {gap["dedupe_key"]: gap for gap in previous}
    merged: list[dict[str, Any]] = []

    for gap in previous:
        key = gap["dedupe_key"]
        if gap["status"] in PRESERVED_STATUSES:
            merged.append(gap)
            continue
        finding = findings.get(key)
        if finding is not None:
            refreshed = dict(finding)
            refreshed["id"] = gap["id"]
            refreshed["answer"] = gap["answer"]
            refreshed["resolution"] = gap["resolution"]
            refreshed["status"] = "open"
            merged.append(refreshed)
            continue
        updated = dict(gap)
        updated["status"] = "stale"
        merged.append(updated)

    for key, finding in findings.items():
        if key in by_key:
            continue
        created = dict(finding)
        created["id"] = str(uuid.uuid4())
        merged.append(created)

    merged.sort(key=lambda gap: (-gap["priority"]["score"], gap["dedupe_key"]))
    document = {"schema_version": 1, "gaps": merged}
    validate_queue(document, data_dir)
    return document


def audit_knowledge(data_dir: Path, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    return merge_findings(data_dir, detect_gaps(data_dir), existing)


def apply_answer(gap: dict[str, Any], answer: str, proposed_edit: str, answered_at: str) -> None:
    """Record an owner answer. A different later edit is kept beside the earlier one."""
    resolution = gap.get("resolution")
    if resolution is None:
        gap["answer"] = answer
        gap["status"] = "answered"
        gap["resolution"] = {
            "proposed_edit": proposed_edit,
            "prior_proposed_edits": [],
            "provenance": "owner_direct",
            "answered_at": answered_at,
            "approved_at": None,
            "index_data_commit": None,
        }
        return
    current = resolution.get("proposed_edit")
    if current == proposed_edit:
        return
    prior = list(resolution.get("prior_proposed_edits") or [])
    if current:
        prior.append(current)
    resolution["prior_proposed_edits"] = prior
    resolution["proposed_edit"] = proposed_edit
    resolution["answered_at"] = answered_at
    gap["resolution"] = resolution
    gap["answer"] = answer
    gap["kind"] = "conflicting"
    gap["status"] = "answered"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GapError(message)


def _source_exists(data_dir: Path, source: str) -> bool:
    return (data_dir / source).is_file()


def validate_queue(document: dict[str, Any], data_dir: Path) -> None:
    """Reject a queue whose evidence files or scores are not usable."""
    _require(document.get("schema_version") == 1, "schema_version must be 1")
    gaps = document.get("gaps")
    _require(isinstance(gaps, list), "gaps must be a list")
    ids: set[str] = set()
    keys: set[str] = set()
    for gap in gaps:
        _require(isinstance(gap, dict), "each gap must be an object")
        gap_id = gap.get("id")
        _require(isinstance(gap_id, str) and gap_id, "gap id must be a non-empty string")
        _require(gap_id not in ids, f"duplicate gap id: {gap_id}")
        ids.add(gap_id)
        dedupe_key = gap.get("dedupe_key")
        _require(isinstance(dedupe_key, str) and dedupe_key, "dedupe_key must be a non-empty string")
        _require(dedupe_key not in keys, f"duplicate dedupe_key: {dedupe_key}")
        keys.add(dedupe_key)
        _require(gap.get("kind") in KINDS, f"invalid kind for {dedupe_key}")
        _require(gap.get("status") in STATUSES, f"invalid status for {dedupe_key}")
        _require(gap.get("created_from") in CREATED_FROM, f"invalid created_from for {dedupe_key}")
        subject = gap.get("subject")
        _require(isinstance(subject, dict), f"subject must be an object for {dedupe_key}")
        source = subject.get("source")
        _require(isinstance(source, str) and _source_exists(data_dir, source), f"missing source file: {source}")
        _require(isinstance(subject.get("section_path"), str), f"section_path missing for {dedupe_key}")
        _require(
            isinstance(subject.get("section_hash"), str) and subject["section_hash"].startswith("sha256:"),
            f"section_hash missing for {dedupe_key}",
        )
        evidence = gap.get("known_evidence")
        _require(isinstance(evidence, list) and evidence, f"known_evidence missing for {dedupe_key}")
        for item in evidence:
            evidence_source = item.get("source")
            _require(
                isinstance(evidence_source, str) and _source_exists(data_dir, evidence_source),
                f"missing evidence file: {evidence_source}",
            )
            _require(isinstance(item.get("section_path"), str), f"evidence section_path missing for {dedupe_key}")
            _require(
                isinstance(item.get("quote_hash"), str) and item["quote_hash"].startswith("sha256:"),
                f"quote_hash missing for {dedupe_key}",
            )
        scores = gap.get("priority")
        _require(isinstance(scores, dict), f"priority missing for {dedupe_key}")
        for field, limit in (
            ("impact", 3),
            ("interview_weight", 3),
            ("misrepresentation_risk", 3),
            ("effort", 2),
        ):
            value = scores.get(field)
            _require(isinstance(value, int) and 0 <= value <= limit, f"priority.{field} out of range for {dedupe_key}")
        expected = (
            scores["impact"]
            + scores["interview_weight"]
            + scores["misrepresentation_risk"]
            - scores["effort"]
        )
        _require(scores.get("score") == expected, f"priority.score does not match the formula for {dedupe_key}")
        _require(isinstance(gap.get("question"), str) and gap["question"].strip(), f"question missing for {dedupe_key}")
        _require(isinstance(gap.get("missing"), str) and gap["missing"].strip(), f"missing text absent for {dedupe_key}")
