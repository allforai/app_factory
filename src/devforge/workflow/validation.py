"""Workflow node graph validation.

Called by wf init (before writing files) and by the planner flow (before
accepting planner output). Raises ValueError describing the first violation found.

knowledge_refs pointing to missing files are warnings only (stderr), not errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

from devforge.workflow.models import NodeDefinition

_VALID_EXECUTORS = {"codex", "claude_code"}


def validate_workflow(nodes: list[NodeDefinition], root: Path | None = None) -> None:
    """Validate node graph. Raises ValueError on the first structural violation.

    Args:
        nodes: list of NodeDefinition to validate.
        root: project root for knowledge_refs existence check (optional; warnings only).
    """
    ids = [n["id"] for n in nodes]

    # Unique IDs
    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            raise ValueError(f"duplicate node id: '{node_id}'")
        seen.add(node_id)

    id_set = set(ids)
    for node in nodes:
        node_id = node["id"]

        # Self-dependency
        if node_id in node.get("depends_on", []):
            raise ValueError(f"node '{node_id}' has self-dependency")

        # Missing dependencies
        for dep in node.get("depends_on", []):
            if dep not in id_set:
                raise ValueError(
                    f"node '{node_id}' depends on '{dep}' which does not exist in the workflow"
                )

        # Valid executor
        if node.get("executor", "codex") not in _VALID_EXECUTORS:
            raise ValueError(
                f"node '{node_id}' has invalid executor '{node['executor']}' "
                f"(must be one of: {sorted(_VALID_EXECUTORS)})"
            )

        # knowledge_refs: warn only
        if root is not None:
            for ref in node.get("knowledge_refs", []):
                if not (root / ref).exists():
                    print(
                        f"WARNING: knowledge_ref '{ref}' for node '{node_id}' not found — skipping",
                        file=sys.stderr,
                    )

    # Cycle detection (DFS)
    adj: dict[str, list[str]] = {n["id"]: list(n.get("depends_on", [])) for n in nodes}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node_id: str) -> None:
        visited.add(node_id)
        in_stack.add(node_id)
        for dep in adj.get(node_id, []):
            if dep not in visited:
                dfs(dep)
            elif dep in in_stack:
                raise ValueError(
                    f"cyclic dependency detected: '{node_id}' -> '{dep}' closes a cycle"
                )
        in_stack.discard(node_id)

    for node_id in ids:
        if node_id not in visited:
            dfs(node_id)
