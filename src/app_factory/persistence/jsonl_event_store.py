"""JSONL-backed append-only event store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlEventStore:
    """Simple append-only event log using newline-delimited JSON."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append_event(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_events(self, *, event_type: str | None = None, scope_id: str | None = None) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event_type is not None and event.get("event_type") != event_type:
                    continue
                if scope_id is not None and event.get("scope_id") != scope_id:
                    continue
                events.append(event)
        return events
