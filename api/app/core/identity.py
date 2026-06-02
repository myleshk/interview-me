"""Core identity data for interview-me.

Single source of truth — reads from ``api/data/identity.json``
at import time.  The LLM receives these core facts in its system prompt
so it never hallucinates personal information.

To update the avatar's identity, edit **``api/data/identity.json``** only.
Rich details (skills, projects, bio, education) live in ``api/data/knowledge/*.md``
and are retrieved via the RAG pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve relative to *this* file: api/app/core/identity.py
#                                   → ../../../data/identity.json
_IDENTITY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "identity.json"


def _load_identity() -> dict[str, Any]:
    """Load the identity JSON file (called once at import time)."""
    if not _IDENTITY_PATH.is_file():
        raise FileNotFoundError(
            f"Identity data not found at {_IDENTITY_PATH}. "
            "Place your structured profile at api/data/identity.json"
        )
    return json.loads(_IDENTITY_PATH.read_text(encoding="utf-8"))


IDENTITY: dict[str, Any] = _load_identity()


def get_identity() -> dict[str, Any]:
    """Return the identity dictionary (FastAPI dependency helper)."""
    return IDENTITY
