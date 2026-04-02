"""Helpers for building executor-facing node knowledge packets."""

from __future__ import annotations

from devforge.knowledge.models import NodeKnowledgePacket


def build_node_knowledge_packet(
    *,
    phase: str,
    goal: str,
    role_id: str | None,
    domain: str | None,
    specialized_knowledge: dict[str, object],
    selected_knowledge_ids: list[str],
    constraints: list[str],
    acceptance: list[str],
) -> NodeKnowledgePacket:
    """Build a layered-disclosure packet for one node execution."""
    brief = "Execute %s work with the current project-specific knowledge focus." % phase
    if goal:
        brief = "%s Goal: %s" % (brief, goal)

    return NodeKnowledgePacket(
        brief=brief,
        focus={
            "phase": phase,
            "role_id": role_id,
            "domain": domain,
            "specialized_knowledge": specialized_knowledge,
        },
        constraints=constraints,
        acceptance=acceptance,
        deep_refs=selected_knowledge_ids,
    )
