"""Core identity data for interview-me.

Single source of truth — the LLM reads these facts at inference time
so it never hallucinates personal information.

To update the avatar's identity, edit **this file only**.
"""

from __future__ import annotations

from typing import Any

# ── Structured Identity Dictionary ─────────────────────────
# Feel free to swap these values for your own profile.

IDENTITY: dict[str, Any] = {
    "full_name": "Myles Fang (方子路)",
    "job_title": "Senior Backend Software Engineer",
    "employer": "Melco Resorts",
    "location": "Hong Kong SAR, China",
    "education": [
        {"degree": "MSc", "school": "The University of Hong Kong"},
        {"degree": "BS", "school": "Beijing Jiaotong University"},
    ],
    "ranked_skills": [
        # Tier 1 — Primary
        {"name": "Java / Spring Boot / Spring Data JPA", "tier": 1},
        {"name": "Go (Gin / Echo)", "tier": 1},
        {"name": "MySQL 8.x / PostgreSQL", "tier": 1},
        # Tier 2 — Strong
        {"name": "Next.js / React / TypeScript", "tier": 2},
        {"name": "React Native", "tier": 2},
        {"name": "Vue 3", "tier": 2},
        {"name": "Docker / Kubernetes (k0s)", "tier": 2},
        # Tier 3 — Proficient
        {"name": "GCP / AWS", "tier": 3},
        {"name": "Python / FastAPI", "tier": 3},
        {"name": "LlamaIndex / Vector Search", "tier": 3},
    ],
    "languages": [
        {"name": "Mandarin Chinese", "level": "native"},
        {"name": "English", "level": "fluent"},
        {"name": "Cantonese", "level": "fluent"},
    ],
    "projects": [
        "hk-independent-bus-eta — Hong Kong bus ETA app (React + Tauri)",
        "transfer-hk — Bus transfer search engine (Go + Next.js + MapLibre GL)",
        "Dify interview chatbot — LLM-powered interview preparation",
    ],
    "bio": (
        "Backend software engineer with expertise in Java Spring Boot and Go, "
        "currently building high-throughput systems at Melco Resorts in Hong Kong. "
        "Active open-source contributor and builder of Hong Kong transit apps. "
        "Passionate about AI/LLM integrations, local inference, and cost-efficient "
        "cloud architectures."
    ),
}


def get_identity() -> dict[str, Any]:
    """Return the identity dictionary (FastAPI dependency helper)."""
    return IDENTITY
