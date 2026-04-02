"""SQLite-backed persistence stores."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .sqlite_schema import sqlite_schema


class _SQLiteStoreBase:
    """Shared SQLite bootstrap and connection helpers."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(sqlite_schema())


class SQLiteSnapshotStore(_SQLiteStoreBase):
    """Snapshot store backed by the SQLite snapshots table."""

    def load_snapshot(self, name: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM snapshots WHERE snapshot_name = ?",
                (name,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(name)
        return json.loads(row[0])

    def save_snapshot(self, name: str, data: dict[str, Any]) -> None:
        payload_json = json.dumps(data, ensure_ascii=False, indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshots(snapshot_name, payload_json, updated_at)
                VALUES(?, ?, datetime('now'))
                ON CONFLICT(snapshot_name)
                DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (name, payload_json),
            )

    def list_snapshots(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT snapshot_name FROM snapshots ORDER BY snapshot_name").fetchall()
        return [row[0] for row in rows]


class SQLiteEventStore(_SQLiteStoreBase):
    """Event store backed by the SQLite events table."""

    def append_event(self, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events(event_id, event_type, scope_id, payload_json, created_at)
                VALUES(?, ?, ?, ?, COALESCE(?, datetime('now')))
                """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["scope_id"],
                    json.dumps(event.get("payload", {}), ensure_ascii=False),
                    event.get("created_at"),
                ),
            )

    def list_events(self, *, event_type: str | None = None, scope_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if scope_id is not None:
            clauses.append("scope_id = ?")
            params.append(scope_id)
        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)
        query = (
            "SELECT event_id, event_type, scope_id, payload_json, created_at"
            f" FROM events{where} ORDER BY created_at, event_id"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "event_id": row[0],
                "event_type": row[1],
                "scope_id": row[2],
                "payload": json.loads(row[3]),
                "created_at": row[4],
            }
            for row in rows
        ]
