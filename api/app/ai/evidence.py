"""Deterministic evidence labels for retrieved chunks.

Scope is derived from the source filename and the heading chain. It is a
fixed label, not a confidence score.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Scope = Literal["inventory", "role", "project", "narrative", "unscoped"]

_INVENTORY_SOURCE = "1_identity_core.md"
_NARRATIVE_SOURCE = "5_engineering_mind.md"
_EXPERIENCE_SOURCE = "2_cv_experience.md"
_BROAD_SCOPES = frozenset({"inventory", "narrative"})
_SPECIFIC_SCOPES = frozenset({"role", "project"})
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATED_HEADING = re.compile(rf"\b{_MONTH}\s+\d{{4}}\b|\bPresent\b", re.IGNORECASE)


class EvidenceItem(BaseModel):
    """One retrieved chunk plus the labels generation is allowed to use."""

    model_config = ConfigDict(frozen=True)

    source: str
    section_path: str
    section_headings: tuple[str, ...]
    content_type: str
    domains: tuple[str, ...]
    sensitivity: str
    scope: Scope
    text: str


class EvidencePacket(BaseModel):
    """Retrieved evidence and the flags that describe the set."""

    model_config = ConfigDict(frozen=True)

    items: tuple[EvidenceItem, ...]
    retrieval_empty: bool
    mixed_scopes: bool
    multi_project: bool
    sensitive: bool
    filtered_domains: tuple[str, ...] = ()
    filter_fallback: bool = False


def _basename(source: str) -> str:
    return source.rsplit("/", 1)[-1]


def heading_chain(section_path: str, section_headings: tuple[str, ...]) -> tuple[str, ...]:
    """Combine the stored section path with headings present in the chunk."""
    parts = [part for part in section_path.split("/") if part]
    for heading in section_headings:
        if not parts or parts[-1] != heading:
            parts.append(heading)
    return tuple(parts)


def classify_scope(source: str, section_path: str, section_headings: tuple[str, ...]) -> Scope:
    """Label a chunk from its filename and heading chain.

    A dated employment heading is a role. A heading nested under a dated
    employment heading is a project. Highlight sections of the identity
    file are an inventory. The engineering-narrative file is narrative.
    Anything else is unscoped.
    """
    filename = _basename(source)
    chain = heading_chain(section_path, section_headings)
    if filename == _NARRATIVE_SOURCE:
        return "narrative"
    if filename == _INVENTORY_SOURCE and any("highlight" in part.lower() for part in chain):
        return "inventory"
    if filename == _EXPERIENCE_SOURCE:
        dated = [index for index, heading in enumerate(chain) if _DATED_HEADING.search(heading)]
        if not dated:
            return "unscoped"
        if dated[-1] == len(chain) - 1:
            return "role"
        return "project"
    return "unscoped"


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def build_evidence_packet(
    payloads: list[dict[str, Any]],
    *,
    filtered_domains: tuple[str, ...] | list[str] = (),
    filter_fallback: bool = False,
) -> EvidencePacket:
    """Build labeled evidence from Qdrant payloads. Empty text is dropped."""
    items: list[EvidenceItem] = []
    for payload in payloads:
        text = payload.get("text") or ""
        if not isinstance(text, str) or not text.strip():
            continue
        metadata = payload.get("document_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        headings = _string_tuple(payload.get("section_headings"))
        section_path = payload.get("section_path") or ""
        if not isinstance(section_path, str):
            section_path = ""
        source = payload.get("source") or "?"
        if not isinstance(source, str):
            source = "?"
        items.append(
            EvidenceItem(
                source=source,
                section_path=section_path,
                section_headings=headings,
                content_type=metadata.get("content_type")
                if isinstance(metadata.get("content_type"), str)
                else "",
                domains=_string_tuple(metadata.get("domains")),
                sensitivity=metadata.get("sensitivity")
                if isinstance(metadata.get("sensitivity"), str)
                else "",
                scope=classify_scope(source, section_path, headings),
                text=text,
            )
        )

    scopes = {item.scope for item in items}
    located = {
        item.section_path or "/".join(item.section_headings) or item.source
        for item in items
        if item.scope in _SPECIFIC_SCOPES
    }
    return EvidencePacket(
        items=tuple(items),
        retrieval_empty=not items,
        mixed_scopes=bool(scopes & _BROAD_SCOPES and scopes & _SPECIFIC_SCOPES),
        multi_project=len(located) >= 2,
        sensitive=any(item.sensitivity == "personal" for item in items),
        filtered_domains=tuple(filtered_domains),
        filter_fallback=filter_fallback,
    )


def render_evidence_item(item: EvidenceItem) -> str:
    """Render one chunk with the labels the prompt requires."""
    headings = " > ".join(item.section_headings) or "-"
    domains = ",".join(item.domains) or "-"
    sensitivity = item.sensitivity or "unknown"
    section = item.section_path or "/"
    header = (
        f"[scope={item.scope} source={item.source} section={section} "
        f"headings={headings} sensitivity={sensitivity} domains={domains}]"
    )
    return f"{header}\n{item.text}"


def render_evidence_block(packet: EvidencePacket) -> str:
    """Render packet flags and labeled chunks."""
    flags = (
        "Evidence flags: "
        f"retrieval_empty={str(packet.retrieval_empty).lower()}; "
        f"mixed_scopes={str(packet.mixed_scopes).lower()}; "
        f"multi_project={str(packet.multi_project).lower()}; "
        f"sensitive={str(packet.sensitive).lower()}"
    )
    body = "\n\n".join(render_evidence_item(item) for item in packet.items)
    return f"{flags}\n\n{body}" if body else flags
