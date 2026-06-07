"""Core identity data for interview-me.

Single source of truth — reads from ``data/identity.json`` at import time.
The LLM receives these core facts in its system prompt so it never
hallucinates personal information.

To update the avatar's identity, edit ``identity.json`` in the
``interview-me-data`` repo.
Rich details (skills, projects, bio, education) live in
``data/knowledge/*.md`` and are indexed by the standalone indexer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Default: api/data/ (works in Docker with ../data:/app/data volume)
# Override: set DATA_DIR=/absolute/path/to/interview-me-data for local dev
_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data"
_BASE = Path(os.environ.get("DATA_DIR", str(_DEFAULT)))
_IDENTITY_PATH = _BASE / "identity.json"


def _load_identity() -> dict[str, Any]:
    """Load the identity JSON file (called once at import time)."""
    if not _IDENTITY_PATH.is_file():
        raise FileNotFoundError(
            f"Identity data not found at {_IDENTITY_PATH}. "
            "Place your identity.json at data/identity.json"
        )
    return json.loads(_IDENTITY_PATH.read_text(encoding="utf-8"))


IDENTITY: dict[str, Any] = _load_identity()


def get_identity() -> dict[str, Any]:
    """Return the identity dictionary (FastAPI dependency helper)."""
    return IDENTITY
