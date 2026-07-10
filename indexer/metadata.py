"""Load and validate explicit metadata for knowledge documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

METADATA_FILENAME = "metadata.json"
_REQUIRED_FIELDS = {
    "content_type": str,
    "domains": list,
    "topics": list,
    "temporal": bool,
    "sensitivity": str,
}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MetadataError(ValueError):
    """Raised when the knowledge metadata manifest is invalid."""


def load_document_metadata(data_dir: Path, markdown_sources: set[str]) -> dict[str, dict[str, Any]]:
    """Return validated per-document metadata with exact Markdown coverage."""
    path = data_dir / METADATA_FILENAME
    if not path.is_file():
        raise MetadataError(f"knowledge metadata not found: {path}")

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetadataError(f"failed to read {path}: {exc}") from exc

    if manifest.get("schema_version") != 1:
        raise MetadataError("metadata.json schema_version must be 1")

    documents = manifest.get("documents")
    if not isinstance(documents, dict):
        raise MetadataError("metadata.json documents must be an object")

    configured_sources = set(documents)
    missing = sorted(markdown_sources - configured_sources)
    unknown = sorted(configured_sources - markdown_sources)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing metadata for: {', '.join(missing)}")
        if unknown:
            details.append(f"metadata references missing files: {', '.join(unknown)}")
        raise MetadataError("; ".join(details))

    validated: dict[str, dict[str, Any]] = {}
    for source, metadata in documents.items():
        if not isinstance(metadata, dict):
            raise MetadataError(f"metadata for {source} must be an object")
        for field, expected_type in _REQUIRED_FIELDS.items():
            value = metadata.get(field)
            if not isinstance(value, expected_type):
                raise MetadataError(
                    f"metadata for {source}.{field} must be {expected_type.__name__}"
                )
        for field in ("domains", "topics"):
            values = metadata[field]
            if not values or any(not isinstance(value, str) or not value.strip() for value in values):
                raise MetadataError(f"metadata for {source}.{field} must contain non-empty strings")
        validated[source] = metadata

    return validated


def extract_section_path(text: str) -> list[str]:
    """Extract the ordered Markdown headings present in one parsed chunk."""
    headings: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line)
        if not match:
            continue
        title = match.group(2).strip().strip("*").strip()
        if title:
            headings.append(title)
    return headings


def build_section_path(parser_path: str, text: str) -> str:
    """Combine parser ancestors with headings present in the current chunk."""
    parts = [part for part in parser_path.split("/") if part]
    for heading in extract_section_path(text):
        if not parts or parts[-1] != heading:
            parts.append(heading)
    return f"/{'/'.join(parts)}" if parts else ""
