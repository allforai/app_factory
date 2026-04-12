"""Workflow engine: node selection, artifact reconciliation, and execution."""

from __future__ import annotations

import copy
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
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
    """Return nodes that are ready to run (pending or retryable-failed + deps met + under concurrency limit)."""
    completed_ids = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running_count = sum(1 for n in manifest["nodes"] if n["status"] == "running")
    slots = MAX_CONCURRENT - running_count
    if slots <= 0:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] in ("pending", "failed")
        and n.get("attempt_count", 0) < MAX_ATTEMPTS
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


_BUILTIN_KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge" / "content"


def _load_knowledge(refs: list[str], root: Path) -> str:
    """Read knowledge_refs files and join their content. Missing files are skipped.

    Resolution order:
    1. Project-local: root / ref
    2. DevForge built-in: strip "knowledge/" prefix, look in package content dir
    """
    parts: list[str] = []
    for ref in refs:
        path = root / ref
        if not path.exists():
            builtin_ref = ref[len("knowledge/"):] if ref.startswith("knowledge/") else ref
            path = _BUILTIN_KNOWLEDGE / builtin_ref
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

_EXECUTOR_TIMEOUT = int(os.environ.get("DEVFORGE_EXECUTOR_TIMEOUT", "600"))


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
        cmd = ["claude", "--print", "--dangerously-skip-permissions", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root, timeout=_EXECUTOR_TIMEOUT)
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or proc.stderr or "").strip(),
        "executor": executor,
    }


def _write_run_log(root: Path, wf_id: str, node_id: str, started_at: str,
                   executor: str, returncode: int, output: str) -> Path:
    """Save executor raw output to .devforge/workflows/<wf-id>/runs/<node>.<ts>.log"""
    runs_dir = root / ".devforge" / "workflows" / wf_id / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    # Use a sortable timestamp slug from started_at
    ts_slug = started_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")[:15]
    log_path = runs_dir / f"{node_id}.{ts_slug}.log"
    lines = [
        f"node:       {node_id}",
        f"executor:   {executor}",
        f"started_at: {started_at}",
        f"exit_code:  {returncode}",
        f"---",
        output or "(no output)",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def _write_status_json(root: Path, wf_id: str, manifest: WorkflowManifest,
                       cycle_dispatched: list[str]) -> None:
    """Write .devforge/workflows/<wf-id>/status.json — machine-readable snapshot for agents."""
    completed = [n for n in manifest["nodes"] if n["status"] == "completed"]
    failed    = [n for n in manifest["nodes"] if n["status"] == "failed"]
    running   = [n for n in manifest["nodes"] if n["status"] == "running"]
    pending   = [n for n in manifest["nodes"] if n["status"] == "pending"]
    total     = len(manifest["nodes"])

    status = {
        "wf_id": wf_id,
        "goal": manifest.get("goal", ""),
        "workflow_status": manifest["workflow_status"],
        "progress": {
            "completed": len(completed),
            "failed": len(failed),
            "running": len(running),
            "pending": len(pending),
            "total": total,
        },
        "active_nodes": [n["id"] for n in running],
        "last_cycle_at": _now(),
        "last_cycle_dispatched": cycle_dispatched,
        "nodes": [
            {
                "id": n["id"],
                "status": n["status"],
                "executor": n.get("executor", "codex"),
                "attempt": n.get("attempt_count", 0),
                "depends_on": n.get("depends_on", []),
                "exit_artifacts": n.get("exit_artifacts", []),
                "started_at": n.get("last_started_at"),
                "completed_at": n.get("last_completed_at"),
                "error": n.get("last_error"),
            }
            for n in manifest["nodes"]
        ],
    }
    status_path = root / ".devforge" / "workflows" / wf_id / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile, os as _os
    fd, tmp = tempfile.mkstemp(dir=str(status_path.parent), suffix=".tmp")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(status, indent=2, ensure_ascii=False))
        _os.replace(tmp, str(status_path))
    except Exception:
        try:
            _os.unlink(tmp)
        except OSError:
            pass


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
        _write_status_json(root, wf_id, manifest, [])
        return {"status": "all_complete", "dispatched": []}

    candidates = select_next_nodes(manifest)
    if not candidates:
        pending = [n["id"] for n in manifest["nodes"] if n["status"] == "pending"]
        running = [n["id"] for n in manifest["nodes"] if n["status"] == "running"]
        if not running:
            exhausted = [
                n["id"] for n in manifest["nodes"]
                if n["status"] == "failed" and n.get("attempt_count", 0) >= MAX_ATTEMPTS
            ]
            if exhausted:
                manifest["workflow_status"] = "failed"
                write_manifest(root, wf_id, manifest)
                _sync_index_status(root, wf_id, "failed")
                _write_status_json(root, wf_id, manifest, [])
                return {"status": "workflow_failed", "dispatched": [], "blocked_by": exhausted}
        write_manifest(root, wf_id, manifest)
        _write_status_json(root, wf_id, manifest, [])
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

            # If this is a planning node, save output as pending_plan.json
            # and transition the workflow to awaiting_confirm
            if node_def.get("mode") == "planning":
                plan_path = root / ".devforge" / "workflows" / wf_id / "pending_plan.json"
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                # Try to extract JSON from output (claude may wrap with extra text)
                saved = False
                if output:
                    # First try: direct JSON parse
                    try:
                        plan_data = json.loads(output)
                        plan_path.write_text(json.dumps(plan_data, indent=2, ensure_ascii=False), encoding="utf-8")
                        saved = True
                    except json.JSONDecodeError:
                        # Second try: find JSON block in output
                        import re
                        match = re.search(r'\{[\s\S]*"nodes"\s*:\s*\[[\s\S]*\]\s*[\s\S]*\}', output)
                        if match:
                            try:
                                plan_data = json.loads(match.group())
                                plan_path.write_text(json.dumps(plan_data, indent=2, ensure_ascii=False), encoding="utf-8")
                                saved = True
                            except json.JSONDecodeError:
                                pass
                if saved:
                    manifest["workflow_status"] = "awaiting_confirm"
                else:
                    # Planning produced no parseable plan — stay in planning for retry
                    entry["last_error"] = "planner output was not valid JSON"
                    entry["status"] = "failed"

            # Save output to artifacts for non-planning nodes
            elif output and node_def.get("exit_artifacts"):
                artifact_path = root / node_def["exit_artifacts"][0]
                try:
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        data = json.loads(output)
                        artifact_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    except json.JSONDecodeError:
                        artifact_path.write_text(output, encoding="utf-8")
                except Exception as e:
                    print(f"Failed to save artifact {artifact_path}: {e}")
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

        # Save raw executor output to runs/<node>.<ts>.log
        _write_run_log(
            root, wf_id, entry["id"], started_at,
            node_def.get("executor", "codex"), returncode, output
        )

        # Check if this node exceeded max attempts → fail the whole workflow
        if entry["status"] == "failed" and entry["attempt_count"] >= MAX_ATTEMPTS:
            manifest["workflow_status"] = "failed"
            write_manifest(root, wf_id, manifest)
            _sync_index_status(root, wf_id, "failed")
            _write_status_json(root, wf_id, manifest, dispatched)
            return {"status": "workflow_failed", "dispatched": dispatched}

    write_manifest(root, wf_id, manifest)
    _write_status_json(root, wf_id, manifest, dispatched)
    return {"status": "ok", "dispatched": dispatched}
