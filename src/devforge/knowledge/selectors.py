"""Context-aware knowledge selection for this project."""

from __future__ import annotations

from devforge.knowledge.registry import KNOWLEDGE_REGISTRY, get_knowledge_document
from devforge.knowledge.models import KnowledgeDocument


def select_knowledge_for_context(
    *,
    project_archetype: str,
    phase: str,
    domain: str | None = None,
    role_id: str | None = None,
    preferred_ids: list[str] | None = None,
    excluded_ids: list[str] | None = None,
) -> list[KnowledgeDocument]:
    """Select local migrated knowledge documents for one orchestration context."""
    selected: list[KnowledgeDocument] = []

    archetype_aliases = {
        "game": "gaming",
    }
    project_archetype = archetype_aliases.get(project_archetype, project_archetype)

    archetype_key = "domain.%s" % project_archetype
    if archetype_key in KNOWLEDGE_REGISTRY:
        selected.append(get_knowledge_document(archetype_key))

    phase_key = "phase.%s" % phase
    if phase_key in KNOWLEDGE_REGISTRY:
        selected.append(get_knowledge_document(phase_key))

    if domain == "frontend" and phase == "implementation":
        selected.append(get_knowledge_document("phase.testing"))
    if role_id == "integration_owner":
        selected.append(get_knowledge_document("phase.testing"))

    deduped: list[KnowledgeDocument] = []
    seen: set[str] = set()
    for doc in selected:
        if doc.doc_id not in seen:
            seen.add(doc.doc_id)
            deduped.append(doc)
    preferred_ids = preferred_ids or []
    excluded = set(excluded_ids or [])
    filtered = [doc for doc in deduped if doc.doc_id not in excluded]

    extras: list[KnowledgeDocument] = []
    seen_filtered = {doc.doc_id for doc in filtered}
    for doc_id in preferred_ids:
        if doc_id in KNOWLEDGE_REGISTRY and doc_id not in seen_filtered and doc_id not in excluded:
            extras.append(get_knowledge_document(doc_id))
    return filtered + extras
