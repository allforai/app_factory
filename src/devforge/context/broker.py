"""On-demand context resolution across knowledge, artifacts, memory, and project state."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from devforge.knowledge import get_knowledge_document
from devforge.persistence import ArtifactStore, MemoryStore

from .models import ResolvedContext


class ContextBroker:
    """Resolve structured refs into pullable context for executor instances."""

    def __init__(
        self,
        *,
        snapshot: dict[str, Any] | None = None,
        artifact_store: ArtifactStore | None = None,
        memory_store: MemoryStore | None = None,
    ) -> None:
        self.snapshot = snapshot or {}
        self.artifact_store = artifact_store
        self.memory_store = memory_store

    def resolve_ref(self, ref: str, *, mode: str = "summary", requester_wp_id: str | None = None) -> ResolvedContext:
        """Resolve one ref into summary/full/structured context."""

        if ref.startswith("knowledge://"):
            return self._resolve_knowledge(ref.split("://", 1)[1], mode=mode, original_ref=ref)
        if ref.startswith("artifact://"):
            return self._resolve_artifact(ref.split("://", 1)[1], mode=mode, original_ref=ref)
        if ref.startswith("memory://"):
            return self._resolve_memory(ref.split("://", 1)[1], mode=mode, original_ref=ref)
        if ref.startswith("project://"):
            return self._resolve_project(ref.split("://", 1)[1], mode=mode, original_ref=ref)
        if ref.startswith("workpackage://"):
            return self._resolve_workpackage(ref.split("://", 1)[1], mode=mode, original_ref=ref, requester_wp_id=requester_wp_id)
        return self._resolve_knowledge(ref, mode=mode, original_ref=ref)

    def resolve_many(self, refs: list[str], *, mode: str = "summary") -> list[ResolvedContext]:
        """Resolve a list of refs."""

        return [self.resolve_ref(ref, mode=mode) for ref in refs]

    def preview_many(self, refs: list[str], *, mode: str = "summary") -> list[dict[str, Any]]:
        """Return lightweight preview items suitable for dispatch payloads."""

        previews: list[dict[str, Any]] = []
        for item in self.resolve_many(refs, mode=mode):
            preview = {
                "ref": item.ref,
                "kind": item.kind,
                "mode": item.mode,
                "title": item.title,
            }
            if item.content:
                preview["content"] = item.content
            if item.structured:
                preview["structured"] = item.structured
            previews.append(preview)
        return previews

    def resolve_context_bundle(
        self,
        refs: list[str],
        *,
        mode: str = "summary",
        budget: int | None = None,
    ) -> list[ResolvedContext]:
        """Resolve refs with a simple budget cap for content-heavy modes."""

        resolved: list[ResolvedContext] = []
        remaining = budget
        for ref in refs:
            item = self.resolve_ref(ref, mode=mode)
            if remaining is not None and mode != "structured":
                content_length = len(item.content)
                if content_length > remaining:
                    item.content = item.content[:remaining]
                    remaining = 0
                else:
                    remaining -= content_length
            resolved.append(item)
            if remaining == 0:
                break
        return resolved

    def _resolve_knowledge(self, doc_id: str, *, mode: str, original_ref: str) -> ResolvedContext:
        doc = get_knowledge_document(doc_id)
        content = doc.summary if mode == "summary" else ""
        if mode == "full" and doc.path:
            with open(doc.path, encoding="utf-8") as handle:
                content = handle.read()
        structured = asdict(doc) if mode == "structured" else {}
        return ResolvedContext(
            ref=original_ref,
            kind="knowledge",
            mode=mode,
            title=doc.title,
            content=content,
            structured=structured,
        )

    def _resolve_artifact(self, path: str, *, mode: str, original_ref: str) -> ResolvedContext:
        if self.artifact_store is None:
            return ResolvedContext(ref=original_ref, kind="artifact", mode=mode, title=path)
        content = self.artifact_store.read_text(path)
        if mode == "summary":
            content = content[:500]
        structured: dict[str, Any] = {}
        if mode == "structured":
            try:
                structured = json.loads(content)
                content = ""
            except json.JSONDecodeError:
                structured = {"path": path}
        return ResolvedContext(
            ref=original_ref,
            kind="artifact",
            mode=mode,
            title=path,
            content=content,
            structured=structured,
        )

    def _resolve_memory(self, locator: str, *, mode: str, original_ref: str) -> ResolvedContext:
        if self.memory_store is None:
            return ResolvedContext(ref=original_ref, kind="memory", mode=mode, title=locator)
        namespace, key = locator.rsplit("/", 1)
        record = self.memory_store.load_memory(namespace, key)
        content = record.get("content", "")
        if mode == "summary":
            content = content[:500]
        structured = record if mode == "structured" else {}
        if mode == "structured":
            content = ""
        return ResolvedContext(
            ref=original_ref,
            kind="memory",
            mode=mode,
            title=key,
            content=content,
            structured=structured,
        )

    def _resolve_project(self, project_id: str, *, mode: str, original_ref: str) -> ResolvedContext:
        project = next((item for item in self.snapshot.get("projects", []) if item.get("project_id") == project_id), {})
        if not project:
            return ResolvedContext(ref=original_ref, kind="project", mode=mode, title=project_id)
        if mode == "structured":
            return ResolvedContext(
                ref=original_ref,
                kind="project",
                mode=mode,
                title=project.get("name", project_id),
                structured=project,
            )
        if mode == "full":
            content = json.dumps(project, ensure_ascii=False, indent=2)
        else:
            content = (
                f"{project.get('name', project_id)} "
                f"[{project.get('project_archetype', '')}] "
                f"phase={project.get('current_phase', '')} "
                f"domains={','.join(project.get('domains', []))}"
            )
        return ResolvedContext(
            ref=original_ref,
            kind="project",
            mode=mode,
            title=project.get("name", project_id),
            content=content,
        )

    def _resolve_workpackage(
        self,
        wp_id: str,
        *,
        mode: str,
        original_ref: str,
        requester_wp_id: str | None,
    ) -> ResolvedContext:
        """Resolve a workpackage:// ref with status-aware permission control."""

        _READABLE_STATUSES = {"completed", "verified", "waiting_review"}

        wp = next(
            (item for item in self.snapshot.get("work_packages", []) if item.get("work_package_id") == wp_id),
            None,
        )
        if wp is None:
            return ResolvedContext(ref=original_ref, kind="workpackage", mode=mode, title=wp_id)

        status = wp.get("status", "")
        is_own = requester_wp_id == wp_id
        if status not in _READABLE_STATUSES and not is_own:
            return ResolvedContext(
                ref=original_ref,
                kind="workpackage",
                mode=mode,
                title=wp_id,
                content="access_denied",
            )

        if mode == "structured":
            return ResolvedContext(
                ref=original_ref,
                kind="workpackage",
                mode=mode,
                title=wp_id,
                structured=wp,
            )
        if mode == "full":
            content = json.dumps(wp, ensure_ascii=False, indent=2)
        else:
            content = (
                f"{wp_id} status={status} goal={wp.get('goal', '')} "
                f"artifacts={','.join(wp.get('artifacts_created', []))}"
            )
        return ResolvedContext(
            ref=original_ref,
            kind="workpackage",
            mode=mode,
            title=wp_id,
            content=content,
        )
