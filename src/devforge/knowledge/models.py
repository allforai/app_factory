"""Knowledge models used by the local migrated knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class KnowledgeDocument:
    """One migrated knowledge asset owned by this project."""

    doc_id: str
    title: str
    category: str
    tags: list[str] = field(default_factory=list)
    path: str = ""
    summary: str = ""


@dataclass(slots=True)
class NodeKnowledgePacket:
    """Layered disclosure packet prepared at node level for executors."""

    brief: str
    focus: dict[str, object] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    deep_refs: list[str] = field(default_factory=list)
