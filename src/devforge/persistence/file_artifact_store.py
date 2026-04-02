"""Filesystem-backed artifact store."""

from __future__ import annotations

from pathlib import Path


class FileArtifactStore:
    """Store text artifacts under a project-controlled root."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: str, content: str) -> str:
        artifact_path = self.root / path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        return str(path)

    def read_text(self, path: str) -> str:
        artifact_path = self.root / path
        return artifact_path.read_text(encoding="utf-8")

    def list_artifacts(self, prefix: str = "") -> list[str]:
        return sorted(
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file() and str(path.relative_to(self.root)).startswith(prefix)
        )
