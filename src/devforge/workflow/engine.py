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


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk.

    For running nodes with a pid, also checks process liveness:
    - Process alive → leave as running
    - Process dead + artifacts present → completed
    - Process dead + artifacts missing → failed

    Planning nodes (mode == "planning") are never reconciled via artifacts.
    Nodes with empty exit_artifacts are not automatically completed.
    """
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node.get("mode") in ("planning", "discovery"):
            continue

        if node["status"] == "running" and node.get("pid") is not None:
            if _is_process_alive(node["pid"]):
                continue
            # Process has exited — fall through to artifact check
            if node["exit_artifacts"] and check_artifacts(root, node["exit_artifacts"]):
                node["status"] = "completed"
                node["last_error"] = None
                node["last_completed_at"] = _now()
                node["pid"] = None
            else:
                node["status"] = "failed"
                node["last_error"] = "process exited without producing exit_artifacts"
                node["last_completed_at"] = _now()
                node["pid"] = None
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


def _build_executor_cmd(node: NodeDefinition, root: Path) -> tuple[list[str], str]:
    """Build the executor command and prompt for a node. Returns (cmd, executor_name)."""
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
    return cmd, executor


def _dispatch_node(node: NodeDefinition, root: Path) -> dict[str, Any]:
    """Call executor subprocess with node goal + knowledge content + non-interactive suffix (blocking)."""
    cmd, executor = _build_executor_cmd(node, root)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root, timeout=_EXECUTOR_TIMEOUT)
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or proc.stderr or "").strip(),
        "executor": executor,
    }


def _dispatch_node_async(
    node: NodeDefinition, root: Path, wf_id: str, started_at: str,
) -> tuple[subprocess.Popen, Path]:
    """Start executor subprocess non-blocking. Returns (process, log_path)."""
    cmd, executor = _build_executor_cmd(node, root)

    runs_dir = root / ".devforge" / "workflows" / wf_id / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = started_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")[:15]
    log_path = runs_dir / f"{node['id']}.{ts_slug}.log"

    log_path.write_text("\n".join([
        f"node:       {node['id']}",
        f"executor:   {executor}",
        f"started_at: {started_at}",
        f"exit_code:  (running...)",
        f"---",
    ]), encoding="utf-8")

    log_fh = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd, cwd=root,
        stdout=log_fh, stderr=subprocess.STDOUT,
        text=True,
    )
    log_fh.close()
    return proc, log_path


def _dispatch_planning_node_with_tools(
    node: NodeDefinition, root: Path, wf_id: str,
) -> dict[str, Any]:
    """Run a planning node with full claude code tool access.

    Claude reads the codebase and writes pending_plan.json directly.
    """
    plan_path = root / ".devforge" / "workflows" / wf_id / "pending_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = f"""{node['goal']}

## Your task as planner

You have full access to the codebase at {root}. Before planning:
1. Run: ls -la {root} to see project structure
2. Read key files: README.md, pyproject.toml/package.json/go.mod (whichever exists), any existing source directories
3. Check if {root}/.devforge/artifacts/codebase_snapshot.json exists and read it for context from previous runs

Then create the execution plan and write it as JSON to this exact path:
{plan_path}

The JSON must have this structure:
{{"nodes": [{{"id": "node-id-slug", "capability": "coding", "goal": "Self-contained goal with exact file paths, function signatures, no ambiguity", "exit_artifacts": ["relative/path/to/output.py"], "knowledge_refs": [], "executor": "claude_code", "mode": null, "depends_on": ["other-node-id"]}}], "summary": "One sentence summary of the plan"}}

Rules:
- Each node goal must be fully self-contained (no "as discussed above" references)
- exit_artifacts paths are relative to {root}
- Use executor="claude_code" for all nodes
- depends_on must reference node ids defined in the same plan
- Write the file, don't print the JSON to stdout
"""
    prompt = prompt + _NON_INTERACTIVE_SUFFIX

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash",
        "-p", prompt,
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True,
            timeout=_EXECUTOR_TIMEOUT,
        )
        return {
            "returncode": proc.returncode,
            "output": (proc.stdout or proc.stderr or "").strip(),
            "executor": "claude_code",
            "plan_written": plan_path.exists(),
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 1, "output": f"planner timeout after {_EXECUTOR_TIMEOUT}s", "executor": "claude_code", "plan_written": False}
    except FileNotFoundError:
        return {"returncode": 1, "output": "claude not found on PATH", "executor": "claude_code", "plan_written": False}


def _dispatch_discovery_node(
    node: NodeDefinition, root: Path,
) -> dict[str, Any]:
    """Run a codebase discovery node with full tool access.

    Claude scans the codebase and writes .devforge/artifacts/codebase_snapshot.json
    with incremental update support.
    """
    snapshot_path = root / ".devforge" / "artifacts" / "codebase_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    existing_snapshot = ""
    if snapshot_path.exists():
        existing_snapshot = f"""
A previous snapshot exists at {snapshot_path}.
Read it first, then only re-scan files that have changed since the snapshot's "scanned_at" timestamp.
Update the snapshot with new/changed files only (incremental update).
"""

    prompt = f"""Analyze the codebase at {root} and write a structured snapshot to {snapshot_path}.

{existing_snapshot}

The snapshot JSON must have this structure:
{{"scanned_at": "ISO timestamp", "root": "{root}", "structure": {{"directories": ["list of key directories"], "entry_points": ["main files, CLI entry points"], "tech_stack": ["Python", "FastAPI", "etc"], "key_files": ["important files to understand the project"]}}, "modules": [{{"path": "relative/path/to/file.py", "purpose": "one line description", "exports": ["function/class names"], "depends_on": ["other/module.py"]}}], "existing_tests": ["list of test files"], "open_todos": ["any TODO/FIXME found in code"]}}

Scan the codebase thoroughly. Read source files. Write the snapshot file directly.
"""
    prompt = prompt + _NON_INTERACTIVE_SUFFIX

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Bash",
        "-p", prompt,
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True,
            timeout=_EXECUTOR_TIMEOUT,
        )
        return {
            "returncode": proc.returncode,
            "output": (proc.stdout or proc.stderr or "").strip(),
            "executor": "claude_code",
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 1, "output": f"discovery timeout after {_EXECUTOR_TIMEOUT}s", "executor": "claude_code"}
    except FileNotFoundError:
        return {"returncode": 1, "output": "claude not found on PATH", "executor": "claude_code"}


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

    from devforge.workflow.graph import run_workflow_cycle
    return run_workflow_cycle(root, wf_id, manifest)
