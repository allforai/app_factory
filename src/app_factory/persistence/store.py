"""Persistence abstractions."""

from __future__ import annotations

from typing import Any, Protocol


class SnapshotStore(Protocol):
    """Protocol for snapshot-oriented persistence backends."""

    def load_snapshot(self, name: str) -> dict[str, Any]:
        """Load a named snapshot document."""

    def save_snapshot(self, name: str, data: dict[str, Any]) -> None:
        """Persist a named snapshot document."""

    def list_snapshots(self) -> list[str]:
        """List known snapshot names."""


class EventStore(Protocol):
    """Append-only event log for orchestration changes and execution history."""

    def append_event(self, event: dict[str, Any]) -> None:
        """Persist a single event record."""

    def list_events(self, *, event_type: str | None = None, scope_id: str | None = None) -> list[dict[str, Any]]:
        """List events filtered by type or scope."""


class ArtifactStore(Protocol):
    """Store for markdown, contracts, reports, and other text artifacts."""

    def write_text(self, path: str, content: str) -> str:
        """Write a text artifact and return its storage path."""

    def read_text(self, path: str) -> str:
        """Read a text artifact by relative storage path."""

    def list_artifacts(self, prefix: str = "") -> list[str]:
        """List known artifact paths."""


class MemoryStore(Protocol):
    """Store for persisted memory records that may later be indexed semantically."""

    def save_memory(
        self,
        namespace: str,
        key: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist one memory record."""

    def load_memory(self, namespace: str, key: str) -> dict[str, Any]:
        """Load one memory record."""

    def list_memories(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List memory records, optionally filtered by namespace."""


Store = SnapshotStore
