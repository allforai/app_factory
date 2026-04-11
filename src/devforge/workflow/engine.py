"""Workflow engine: node selection, artifact reconciliation, and execution."""

from __future__ import annotations

import copy
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devforge.workflow.artifacts import check_artifacts
from devforge.executors.subprocess_transport import build_codex_command
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    TransitionEntry,
    WorkflowManifest,
    WorkflowStatus,
)
from devforge.workflow.store import (
    active_workflow_id,
    append_transition,
    read_index,
    read_manifest,
    read_node,
    write_index,
    write_manifest,
)

MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3


def select_next_nodes(manifest: WorkflowManifest) -> list[NodeManifestEntry]:
    """Return nodes that are ready to run (pending + deps met + under concurrency limit)."""
    completed_ids = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running_count = sum(1 for n in manifest["nodes"] if n["status"] == "running")
    slots = MAX_CONCURRENT - running_count
    if slots <= 0:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] == "pending"
        and set(n.get("depends_on", [])) <= completed_ids
    ][:slots]


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk.

    Planning nodes (mode == "planning") are never reconciled via artifacts.
    Nodes with empty exit_artifacts are not automatically completed.
    """
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node.get("mode") == "planning":
            continue
        if node["status"] in ("pending", "running") and node["exit_artifacts"]:
            if check_artifacts(root, node["exit_artifacts"]):
                node["status"] = "completed"
                node["last_error"] = None
    return updated


def _load_knowledge(refs: list[str], root: Path) -> str:
    """Read knowledge_refs files and join their content. Missing files are skipped."""
    parts: list[str] = []
    for ref in refs:
        path = root / ref
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


_NON_INTERACTIVE_SUFFIX = """
---
执行约束（必须遵守）：
- 直接完成任务，不要询问任何确认或补充信息
- 若信息不足，根据已有代码和上下文做出最佳判断并继续
- 不要暂停等待用户输入
- 不要提问，不要要求审查
"""

_EXECUTOR_TIMEOUT = 300  # seconds


def _dispatch_node(node: NodeDefinition, root: Path) -> dict[str, Any]:
    """Call executor subprocess with node goal + knowledge content + non-interactive suffix."""
    knowledge = _load_knowledge(node.get("knowledge_refs", []), root)
    prompt = node["goal"]
    if knowledge:
        prompt = f"{prompt}\n\n---\n\n{knowledge}"
    prompt = prompt + _NON_INTERACTIVE_SUFFIX
    executor = node.get("executor", "codex")
    if executor == "codex":
        cmd = build_codex_command(prompt=prompt, working_dir=str(root))
    else:
        cmd = ["claude", "--print", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root, timeout=_EXECUTOR_TIMEOUT)
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or proc.stderr or "").strip(),
        "executor": executor,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_index_status(root: Path, wf_id: str, status: WorkflowStatus) -> None:
    """Update the index entry status for a workflow."""
    index = read_index(root)
    for entry in index["workflows"]:
        if entry["id"] == wf_id:
            entry["status"] = status
            break
    write_index(root, index)


def run_one_cycle(root: Path) -> dict[str, Any]:
    """Execute one workflow cycle: reconcile → select → dispatch → persist."""
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return {"status": "no_active_workflow", "dispatched": []}

    try:
        manifest = read_manifest(root, wf_id)
    except FileNotFoundError:
        return {"status": "manifest_missing", "dispatched": []}

    # Human-in-the-loop gate: planner ran, waiting for user confirmation
    if manifest["workflow_status"] == "awaiting_confirm":
        return {"status": "awaiting_confirm", "dispatched": []}

    manifest = reconcile_artifacts(root, manifest)

    all_done = all(n["status"] == "completed" for n in manifest["nodes"])
    if all_done and manifest["nodes"]:
        manifest["workflow_status"] = "complete"
        write_manifest(root, wf_id, manifest)
        _sync_index_status(root, wf_id, "complete")
        return {"status": "all_complete", "dispatched": []}

    candidates = select_next_nodes(manifest)
    if not candidates:
        pending = [n["id"] for n in manifest["nodes"] if n["status"] == "pending"]
        running = [n["id"] for n in manifest["nodes"] if n["status"] == "running"]
        write_manifest(root, wf_id, manifest)
        return {"status": "blocked", "dispatched": [], "pending": pending, "running": running}

    dispatched: list[str] = []
    for entry in candidates:
        node_def = read_node(root, wf_id, entry["id"])
        started_at = _now()

        # mark running and increment attempt_count
        entry["status"] = "running"
        entry["attempt_count"] = entry.get("attempt_count", 0) + 1
        entry["last_started_at"] = started_at
        write_manifest(root, wf_id, manifest)

        try:
            result = _dispatch_node(node_def, root)
            returncode = result["returncode"]
            output = result.get("output", "")
        except FileNotFoundError:
            returncode = 1
            output = f"executor not found: {node_def.get('executor', 'codex')}"
        except subprocess.TimeoutExpired:
            returncode = 1
            output = f"executor timeout after {_EXECUTOR_TIMEOUT}s"

        completed_at = _now()
        entry["last_completed_at"] = completed_at

        if returncode == 0:
            entry["status"] = "completed"
            entry["last_error"] = None
        else:
            entry["status"] = "failed"
            entry["last_error"] = output[:500] if output else "non-zero exit"

        transition: TransitionEntry = {
            "node": entry["id"],
            "status": "completed" if returncode == 0 else "failed",
            "started_at": started_at,
            "completed_at": completed_at,
            "artifacts_created": node_def.get("exit_artifacts", []),
            "error": entry["last_error"],
        }
        append_transition(root, wf_id, transition)
        dispatched.append(entry["id"])

        # Check if this node exceeded max attempts → fail the whole workflow
        if entry["status"] == "failed" and entry["attempt_count"] >= MAX_ATTEMPTS:
            manifest["workflow_status"] = "failed"
            write_manifest(root, wf_id, manifest)
            _sync_index_status(root, wf_id, "failed")
            return {"status": "workflow_failed", "dispatched": dispatched}

    write_manifest(root, wf_id, manifest)
    return {"status": "ok", "dispatched": dispatched}
