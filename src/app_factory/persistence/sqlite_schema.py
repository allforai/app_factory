"""SQLite schema for durable state, events, artifacts, and memory."""

from __future__ import annotations


SQLITE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        snapshot_name TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        updated_at TEXT
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        scope_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_events_scope_type
    ON events(scope_id, event_type)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_path TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        updated_at TEXT
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS memories (
        namespace TEXT NOT NULL,
        memory_key TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        updated_at TEXT,
        PRIMARY KEY(namespace, memory_key)
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_memories_namespace
    ON memories(namespace)
    """.strip(),
]


def sqlite_schema() -> str:
    """Return the full SQLite schema as one executable script."""
    return ";\n\n".join(SQLITE_SCHEMA_STATEMENTS) + ";"
