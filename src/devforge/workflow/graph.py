"""LangGraph StateGraph implementation of the workflow engine cycle."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import devforge.workflow.engine as _engine
from devforge.workflow.engine import (
    MAX_ATTEMPTS,
    _now,
    _sync_index_status,
    _write_run_log,
    _write_status_json,
    reconcile_artifacts,
    select_next_nodes,
)
from devforge.workflow.store import (
    append_transition,
    read_manifest,
    read_node,
    write_manifest,
)


class WorkflowState(TypedDict):
    root: str
    wf_id: str
    manifest: dict
    candidates: list
    dispatched: list
    cycle_result: str
    blocked_by: list


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def load_manifest_node(state: WorkflowState) -> dict:
    manifest = read_manifest(Path(state["root"]), state["wf_id"])
    return {"manifest": manifest}


def reconcile_node(state: WorkflowState) -> dict:
    updated = reconcile_artifacts(Path(state["root"]), state["manifest"])
    return {"manifest": updated}


def select_nodes_node(state: WorkflowState) -> dict:
    candidates = select_next_nodes(state["manifest"])
    return {"candidates": candidates}


def _dispatch_planning_node(
    entry: dict, node_def: dict, root: Path, wf_id: str, manifest: dict,
    started_at: str, dispatched: list[str],
) -> dict | None:
    """Dispatch a planning node with full tool access. Returns early-exit dict or None."""
    result = _engine._dispatch_planning_node_with_tools(node_def, root, wf_id)
    returncode = result["returncode"]
    output = result.get("output", "")
    plan_written = result.get("plan_written", False)

    completed_at = _now()
    entry["last_completed_at"] = completed_at

    if returncode == 0 and plan_written:
        entry["status"] = "completed"
        entry["last_error"] = None
        manifest["workflow_status"] = "awaiting_confirm"
    elif returncode == 0 and not plan_written:
        entry["status"] = "failed"
        entry["last_error"] = "planner exited 0 but did not write pending_plan.json"
    else:
        entry["status"] = "failed"
        entry["last_error"] = output[:500] if output else "non-zero exit"

    transition = {
        "node": entry["id"],
        "status": entry["status"],
        "started_at": started_at,
        "completed_at": completed_at,
        "artifacts_created": node_def.get("exit_artifacts", []),
        "error": entry["last_error"],
    }
    append_transition(root, wf_id, transition)
    dispatched.append(entry["id"])

    _write_run_log(
        root, wf_id, entry["id"], started_at,
        result.get("executor", "claude_code"), returncode, output,
    )

    if entry["status"] == "failed" and entry["attempt_count"] >= MAX_ATTEMPTS:
        manifest["workflow_status"] = "failed"
        write_manifest(root, wf_id, manifest)
        _sync_index_status(root, wf_id, "failed")
        _write_status_json(root, wf_id, manifest, dispatched)
        return {"manifest": manifest, "dispatched": dispatched, "cycle_result": "workflow_failed"}
    return None


def _dispatch_discovery_node_sync(
    entry: dict, node_def: dict, root: Path, wf_id: str, manifest: dict,
    started_at: str, dispatched: list[str],
) -> dict | None:
    """Dispatch a discovery node synchronously. Returns early-exit dict or None."""
    result = _engine._dispatch_discovery_node(node_def, root)
    returncode = result["returncode"]
    output = result.get("output", "")

    completed_at = _now()
    entry["last_completed_at"] = completed_at

    if returncode == 0:
        entry["status"] = "completed"
        entry["last_error"] = None
    else:
        entry["status"] = "failed"
        entry["last_error"] = output[:500] if output else "non-zero exit"

    transition = {
        "node": entry["id"],
        "status": entry["status"],
        "started_at": started_at,
        "completed_at": completed_at,
        "artifacts_created": node_def.get("exit_artifacts", []),
        "error": entry["last_error"],
    }
    append_transition(root, wf_id, transition)
    dispatched.append(entry["id"])

    _write_run_log(
        root, wf_id, entry["id"], started_at,
        result.get("executor", "claude_code"), returncode, output,
    )

    if entry["status"] == "failed" and entry["attempt_count"] >= MAX_ATTEMPTS:
        manifest["workflow_status"] = "failed"
        write_manifest(root, wf_id, manifest)
        _sync_index_status(root, wf_id, "failed")
        _write_status_json(root, wf_id, manifest, dispatched)
        return {"manifest": manifest, "dispatched": dispatched, "cycle_result": "workflow_failed"}
    return None


def dispatch_nodes_node(state: WorkflowState) -> dict:
    root = Path(state["root"])
    wf_id = state["wf_id"]
    manifest = state["manifest"]
    dispatched: list[str] = []

    for entry in state["candidates"]:
        node_def = read_node(root, wf_id, entry["id"])
        started_at = _now()

        entry["status"] = "running"
        entry["attempt_count"] = entry.get("attempt_count", 0) + 1
        entry["last_started_at"] = started_at

        if node_def.get("mode") == "planning":
            write_manifest(root, wf_id, manifest)
            early = _dispatch_planning_node(
                entry, node_def, root, wf_id, manifest, started_at, dispatched,
            )
            if early is not None:
                return early
        elif node_def.get("mode") == "discovery":
            write_manifest(root, wf_id, manifest)
            early = _dispatch_discovery_node_sync(
                entry, node_def, root, wf_id, manifest, started_at, dispatched,
            )
            if early is not None:
                return early
        else:
            try:
                proc, log_path = _engine._dispatch_node_async(node_def, root, wf_id, started_at)
                entry["pid"] = proc.pid
                entry["log_path"] = str(log_path)
            except FileNotFoundError:
                entry["status"] = "failed"
                entry["last_error"] = f"executor not found: {node_def.get('executor', 'codex')}"
                entry["pid"] = None
                entry["log_path"] = None
            write_manifest(root, wf_id, manifest)
            dispatched.append(entry["id"])

    return {"manifest": manifest, "dispatched": dispatched, "cycle_result": "ok"}


def persist_node(state: WorkflowState) -> dict:
    root = Path(state["root"])
    wf_id = state["wf_id"]
    write_manifest(root, wf_id, state["manifest"])
    _write_status_json(root, wf_id, state["manifest"], state["dispatched"])
    return {}


def finalize_complete_node(state: WorkflowState) -> dict:
    root = Path(state["root"])
    wf_id = state["wf_id"]
    manifest = state["manifest"]
    manifest["workflow_status"] = "complete"
    write_manifest(root, wf_id, manifest)
    _sync_index_status(root, wf_id, "complete")
    _write_status_json(root, wf_id, manifest, [])
    return {"manifest": manifest, "cycle_result": "all_complete"}


def finalize_awaiting_node(state: WorkflowState) -> dict:
    return {"cycle_result": "awaiting_confirm"}


def finalize_failed_node(state: WorkflowState) -> dict:
    root = Path(state["root"])
    wf_id = state["wf_id"]
    manifest = state["manifest"]
    manifest["workflow_status"] = "failed"
    write_manifest(root, wf_id, manifest)
    _sync_index_status(root, wf_id, "failed")
    _write_status_json(root, wf_id, manifest, [])
    return {"manifest": manifest, "cycle_result": "workflow_failed", "blocked_by": state["blocked_by"]}


def finalize_blocked_node(state: WorkflowState) -> dict:
    root = Path(state["root"])
    wf_id = state["wf_id"]
    manifest = state["manifest"]
    write_manifest(root, wf_id, manifest)
    _write_status_json(root, wf_id, manifest, [])
    return {"cycle_result": "blocked"}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_reconcile(state: WorkflowState) -> str:
    manifest = state["manifest"]
    if manifest["workflow_status"] == "awaiting_confirm":
        return "finalize_awaiting"
    if manifest["nodes"] and all(n["status"] == "completed" for n in manifest["nodes"]):
        return "finalize_complete"
    return "select_nodes"


def route_after_select(state: WorkflowState) -> str:
    if state["candidates"]:
        return "dispatch_nodes"
    running = [n for n in state["manifest"]["nodes"] if n["status"] == "running"]
    if not running:
        exhausted = [
            n["id"] for n in state["manifest"]["nodes"]
            if n["status"] == "failed" and n.get("attempt_count", 0) >= MAX_ATTEMPTS
        ]
        if exhausted:
            state["blocked_by"] = exhausted
            return "finalize_failed"
    return "finalize_blocked"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_workflow_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("load_manifest", load_manifest_node)
    graph.add_node("reconcile", reconcile_node)
    graph.add_node("select_nodes", select_nodes_node)
    graph.add_node("dispatch_nodes", dispatch_nodes_node)
    graph.add_node("persist", persist_node)
    graph.add_node("finalize_complete", finalize_complete_node)
    graph.add_node("finalize_awaiting", finalize_awaiting_node)
    graph.add_node("finalize_failed", finalize_failed_node)
    graph.add_node("finalize_blocked", finalize_blocked_node)

    graph.add_edge(START, "load_manifest")
    graph.add_edge("load_manifest", "reconcile")
    graph.add_conditional_edges("reconcile", route_after_reconcile, {
        "finalize_awaiting": "finalize_awaiting",
        "finalize_complete": "finalize_complete",
        "select_nodes": "select_nodes",
    })
    graph.add_conditional_edges("select_nodes", route_after_select, {
        "dispatch_nodes": "dispatch_nodes",
        "finalize_failed": "finalize_failed",
        "finalize_blocked": "finalize_blocked",
    })
    graph.add_edge("dispatch_nodes", "persist")
    graph.add_edge("persist", END)
    graph.add_edge("finalize_complete", END)
    graph.add_edge("finalize_awaiting", END)
    graph.add_edge("finalize_failed", END)
    graph.add_edge("finalize_blocked", END)

    return graph.compile()


_graph = build_workflow_graph()


def run_workflow_cycle(root: Path, wf_id: str, manifest: dict) -> dict:
    initial_state = WorkflowState(
        root=str(root), wf_id=wf_id, manifest=manifest,
        candidates=[], dispatched=[], cycle_result="", blocked_by=[],
    )
    final_state = _graph.invoke(initial_state)
    result = {"status": final_state["cycle_result"], "dispatched": final_state["dispatched"]}
    if final_state.get("blocked_by"):
        result["blocked_by"] = final_state["blocked_by"]
    return result
