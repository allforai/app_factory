"""Persistence-layer records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EventRecord:
    """Append-only orchestration event."""

    event_id: str
    event_type: str
    scope_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None


@dataclass(slots=True)
class MemoryRecord:
    """Persisted memory entry for user, initiative, project, or executor scope."""

    namespace: str
    key: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactRecord:
    """Stored artifact metadata."""

    path: str
    kind: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)
