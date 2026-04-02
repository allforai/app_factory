"""JSON-backed memory store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonMemoryStore:
    """Structured memory store for global, initiative, project, and executor memory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, namespace: str, key: str) -> Path:
        safe_namespace = namespace.replace("/", "__")
        return self.root / safe_namespace / f"{key}.json"

    def save_memory(
        self,
        namespace: str,
        key: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        path = self._path_for(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "namespace": namespace,
                    "key": key,
                    "content": content,
                    "metadata": metadata or {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def load_memory(self, namespace: str, key: str) -> dict[str, Any]:
        path = self._path_for(namespace, key)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_memories(self, namespace: str | None = None) -> list[dict[str, Any]]:
        root = self.root
        if namespace is not None:
            root = self.root / namespace.replace("/", "__")
            if not root.exists():
                return []
        memories: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*.json")):
            memories.append(json.loads(path.read_text(encoding="utf-8")))
        return memories
