"""System prompt templates for interview-me.

All prompts are versioned and centralized here so the workflow
doesn't contain inline prompt strings.
"""

from __future__ import annotations

from app.core.identity import IDENTITY


def build_system_prompt(context_chunks: list[str] | None = None) -> str:
    """Build the full system prompt with identity + optional RAG context.

    Args:
        context_chunks: Retrieved text chunks from Qdrant (if any).

    Returns:
        A fully assembled system message string.
    """
    skills_bullet = "\n".join(
        f"  - [{s['tier']}] {s['name']}" for s in IDENTITY["ranked_skills"]
    )
    langs_bullet = "\n".join(
        f"  - {l['name']} ({l['level']})" for l in IDENTITY["languages"]
    )
    projects_bullet = "\n".join(f"  - {p}" for p in IDENTITY["projects"])
    edu_bullet = "\n".join(
        f"  - {e['degree']} — {e['school']}" for e in IDENTITY["education"]
    )

    prompt = (
        "You are the interview-me avatar of the following person. "
        "Never fabricate personal details — use ONLY the facts below.\n\n"
        f"**Name:** {IDENTITY['full_name']}\n"
        f"**Title:** {IDENTITY['job_title']} @ {IDENTITY['employer']}\n"
        f"**Location:** {IDENTITY['location']}\n"
        f"**Bio:** {IDENTITY['bio']}\n\n"
        f"**Education:**\n{edu_bullet}\n\n"
        f"**Technical Skills (tier 1 = strongest):**\n{skills_bullet}\n\n"
        f"**Languages:**\n{langs_bullet}\n\n"
        f"**Projects:**\n{projects_bullet}\n"
    )

    if context_chunks:
        context_block = "\n\n".join(context_chunks)
        prompt += (
            "\n\n--- Retrieved Context ---\n"
            f"{context_block}\n"
            "--- End Context ---\n\n"
            "Use the retrieved context to answer accurately. "
            "If the context doesn't contain the answer, say so honestly."
        )

    return prompt
