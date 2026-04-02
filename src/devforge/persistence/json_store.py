"""JSON file-backed snapshot store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devforge.planning import apply_patch_operations


class JsonStore:
    """Simple JSON-backed snapshot store for fixtures and runtime state."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        filename = name if name.endswith(".json") else "%s.json" % name
        return self.root / filename

    def load_snapshot(self, name: str) -> dict[str, Any]:
        path = self._path_for(name)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_snapshot(self, name: str, data: dict[str, Any]) -> None:
        path = self._path_for(name)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def list_snapshots(self) -> list[str]:
        return sorted(path.name for path in self.root.glob("*.json"))

    def apply_patch(self, name: str, operations: list[dict[str, Any]], *, save_as: str | None = None) -> dict[str, Any]:
        """Load a snapshot, apply graph patch operations, and persist the result."""
        snapshot = self.load_snapshot(name)
        updated = apply_patch_operations(snapshot, operations)
        self.save_snapshot(save_as or name, updated)
        return updated

