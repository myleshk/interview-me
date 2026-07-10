"""Deterministic query classification for metadata-aware retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass


_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "identity": (
        "who are you",
        "introduce yourself",
        "tell me about yourself",
        "professional summary",
        "background summary",
    ),
    "skills": (
        "skill",
        "skills",
        "technology",
        "technologies",
        "tech stack",
        "framework",
        "frameworks",
        "programming",
        "technical strengths",
    ),
    "languages": (
        "spoken language",
        "spoken languages",
        "language proficiency",
        "languages do you speak",
        "fluent",
        "fluency",
    ),
    "experience": (
        "experience",
        "employment",
        "career history",
        "work history",
        "worked at",
        "worked for",
        "previous role",
        "previous roles",
        "responsibilities",
    ),
    "projects": (
        "project",
        "projects",
        "worked on",
        "built",
        "developed",
        "portfolio",
    ),
    "education": (
        "education",
        "degree",
        "degrees",
        "university",
        "college",
        "academic",
        "studied",
        "school",
    ),
    "logistics": (
        "relocation",
        "relocate",
        "visa",
        "work authorization",
        "notice period",
        "availability",
        "interview schedule",
        "remote work",
        "hybrid work",
        "onsite work",
    ),
    "culture": (
        "company culture",
        "workplace culture",
        "target company",
        "work environment",
    ),
    "personal": (
        "hobby",
        "hobbies",
        "personal life",
        "free time",
        "outside work",
    ),
    "engineering": (
        "engineering philosophy",
        "problem solving",
        "technical challenge",
        "technical challenges",
        "war story",
        "system design",
        "architecture decision",
        "architecture decisions",
    ),
    "leadership": (
        "leadership",
        "management style",
        "team dynamics",
        "mentoring",
        "mentor",
        "led a team",
    ),
    "career_goals": (
        "career goal",
        "career goals",
        "future role",
        "next role",
        "looking for",
        "career direction",
    ),
    "compensation": (
        "compensation",
        "salary",
        "salary expectations",
        "pay expectations",
        "remuneration",
        "benefits package",
    ),
}


@dataclass(frozen=True)
class QueryClassification:
    """Metadata domains selected from explicit terms in a query."""

    domains: tuple[str, ...]
    matched_terms: dict[str, tuple[str, ...]]


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def classify_query(query: str) -> QueryClassification:
    """Classify a query into filterable knowledge domains.

    No domain is selected when the query has no explicit signal. In that case
    retrieval stays unfiltered.
    """
    normalized = f" {_normalize(query)} "
    matches: dict[str, tuple[str, ...]] = {}

    for domain, terms in _DOMAIN_TERMS.items():
        matched = tuple(term for term in terms if f" {_normalize(term)} " in normalized)
        if matched:
            matches[domain] = matched

    return QueryClassification(domains=tuple(matches), matched_terms=matches)
