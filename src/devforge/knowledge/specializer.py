"""Project-specific knowledge specialization helpers."""

from __future__ import annotations

from devforge.knowledge.registry import get_knowledge_document


def build_specialized_knowledge(
    *,
    project_archetype: str,
    phase: str,
    selected_knowledge_ids: list[str],
    domain: str | None = None,
    role_id: str | None = None,
) -> dict[str, object]:
    """Build a project-specific knowledge pack from selected knowledge ids."""
    documents = [get_knowledge_document(doc_id) for doc_id in selected_knowledge_ids]
    summaries = [doc.summary for doc in documents]
    tags = sorted({tag for doc in documents for tag in doc.tags})

    focus = [project_archetype, phase]
    if domain:
        focus.append(domain)
    if role_id:
        focus.append(role_id)

    return {
        "focus": focus,
        "knowledge_ids": selected_knowledge_ids,
        "titles": [doc.title for doc in documents],
        "tags": tags,
        "summary": " | ".join(summaries),
    }
