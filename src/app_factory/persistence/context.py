"""Aggregated persistence context for orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .file_artifact_store import FileArtifactStore
from .json_memory_store import JsonMemoryStore
from .sqlite_store import SQLiteEventStore, SQLiteSnapshotStore
from .store import ArtifactStore, EventStore, MemoryStore, SnapshotStore


@dataclass(slots=True)
class WorkspacePersistence:
    """Optional grouped persistence services injected into orchestration runtime."""

    snapshot_store: SnapshotStore | None = None
    event_store: EventStore | None = None
    artifact_store: ArtifactStore | None = None
    memory_store: MemoryStore | None = None


def build_local_workspace_persistence(root: str | Path) -> WorkspacePersistence:
    """Build the default local durable persistence layout for a workspace."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    db_path = root_path / "workspace.sqlite3"
    return WorkspacePersistence(
        snapshot_store=SQLiteSnapshotStore(db_path),
        event_store=SQLiteEventStore(db_path),
        artifact_store=FileArtifactStore(root_path / "artifacts"),
        memory_store=JsonMemoryStore(root_path / "memory"),
    )
