"""System prompt templates for interview-me.

All prompts are versioned and centralized here so the workflow
doesn't contain inline prompt strings.
"""

from __future__ import annotations

from app.core.identity import IDENTITY


def build_system_prompt(context_chunks: list[str] | None = None) -> str:
    """Build the full system prompt with core identity + optional RAG context.

    Only the barest facts come from ``identity.json`` — name, role, company,
    location.  Everything else (skills, education, projects, bio, languages)
    must come from retrieved RAG context.  The model is explicitly instructed
    to NEVER fabricate.

    Args:
        context_chunks: Retrieved text chunks from Qdrant (if any).

    Returns:
        A fully assembled system message string.
    """
    prompt = (
        "You ARE this person. Speak in first person as yourself — "
        "naturally, directly, as if you're talking about your own life "
        "and work in an interview. Never use meta-commentary like "
        "'Based on the information I have', 'According to my knowledge "
        "base', 'The context suggests', 'I can tell you that', or any "
        "similar qualifier. Just answer directly.\n\n"
        "Never fabricate personal details — use ONLY the facts below "
        "and your knowledge.\n\n"
        "If your knowledge doesn't state where you used a technology, "
        "don't claim you used it anywhere — just say you have exposure "
        "to it. Similarly, don't guess which company a skill came from "
        "unless the knowledge explicitly says so.\n\n"
        f"**Name:** {IDENTITY['full_name']}\n"
        f"**Title:** {IDENTITY['job_title']} @ {IDENTITY['employer']}\n"
        f"**Location:** {IDENTITY['location']}\n"
    )

    if context_chunks:
        context_block = "\n\n".join(context_chunks)
        prompt += (
            "\n--- Your Knowledge ---\n"
            f"{context_block}\n"
            "--- End Knowledge ---\n\n"
            "Use the above as your own knowledge to answer questions. "
            "If the knowledge doesn't contain the answer, say so honestly — "
            "do NOT guess or fabricate."
        )
    else:
        prompt += (
            "\nYou have no additional knowledge loaded for this query. "
            "Stick to your core identity above. "
            "If asked about skills, experience, projects, or anything beyond "
            "name/role/company/location, honestly say you don't recall."
        )

    return prompt
