"""Tests for the LangGraph workflow graph dispatch logic."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from devforge.workflow.models import NodeDefinition, NodeManifestEntry, WorkflowManifest, WorkflowIndex
from devforge.workflow.store import write_index, write_manifest, write_node, read_manifest
from devforge.workflow.engine import run_one_cycle


def _node(
    node_id: str,
    status: str = "pending",
    depends_on: list[str] | None = None,
    exit_artifacts: list[str] | None = None,
    mode: str | None = None,
    attempt_count: int = 0,
    executor: str = "claude_code",
) -> NodeManifestEntry:
    return {
        "id": node_id,
        "status": status,
        "depends_on": depends_on or [],
        "exit_artifacts": exit_artifacts or [],
        "executor": executor,
        "mode": mode,
        "parent_node_id": None,
        "depth": 0,
        "attempt_count": attempt_count,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
        "pid": None,
        "log_path": None,
    }


def _setup(tmp_path: Path, nodes: list[NodeManifestEntry], node_defs: list[NodeDefinition],
           phase: str = "running") -> str:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)
    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": phase,
        "nodes": nodes,
    }
    write_manifest(tmp_path, wf_id, manifest)
    for nd in node_defs:
        write_node(tmp_path, wf_id, nd)
    return wf_id


# ---------------------------------------------------------------------------
# Planning node with tools — graph-level
# ---------------------------------------------------------------------------


def test_graph_planning_node_checks_plan_written(tmp_path: Path) -> None:
    """Planning node success is determined by plan_written, not stdout JSON."""
    nodes = [_node("planner", mode="planning")]
    node_defs = [NodeDefinition(
        id="planner", capability="planning", goal="plan",
        exit_artifacts=[], knowledge_refs=[], executor="claude_code",
        mode="planning", depends_on=[],
    )]
    wf_id = _setup(tmp_path, nodes, node_defs, phase="planning")
    plan_path = tmp_path / ".devforge" / "workflows" / wf_id / "pending_plan.json"

    def fake_dispatch(node_def, root, wf_id_arg):
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text('{"nodes":[], "summary":"test"}')
        return {"returncode": 0, "output": "done", "executor": "claude_code", "plan_written": True}

    with patch("devforge.workflow.graph._engine._dispatch_planning_node_with_tools", side_effect=fake_dispatch):
        result = run_one_cycle(tmp_path)
    assert "planner" in result["dispatched"]
    manifest = read_manifest(tmp_path, wf_id)
    assert manifest["workflow_status"] == "awaiting_confirm"
    planner = manifest["nodes"][0]
    assert planner["status"] == "completed"


def test_graph_planning_node_fails_when_plan_not_written(tmp_path: Path) -> None:
    """Planning node fails if returncode=0 but plan file was not written."""
    nodes = [_node("planner", mode="planning")]
    node_defs = [NodeDefinition(
        id="planner", capability="planning", goal="plan",
        exit_artifacts=[], knowledge_refs=[], executor="claude_code",
        mode="planning", depends_on=[],
    )]
    wf_id = _setup(tmp_path, nodes, node_defs, phase="planning")

    def fake_dispatch(node_def, root, wf_id_arg):
        return {"returncode": 0, "output": "oops", "executor": "claude_code", "plan_written": False}

    with patch("devforge.workflow.graph._engine._dispatch_planning_node_with_tools", side_effect=fake_dispatch):
        result = run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, wf_id)
    planner = manifest["nodes"][0]
    assert planner["status"] == "failed"
    assert "pending_plan.json" in (planner["last_error"] or "")


# ---------------------------------------------------------------------------
# Discovery node — graph-level
# ---------------------------------------------------------------------------


def test_graph_discovery_node_dispatched(tmp_path: Path) -> None:
    """Discovery nodes are routed to _dispatch_discovery_node."""
    nodes = [_node("discover", mode="discovery")]
    node_defs = [NodeDefinition(
        id="discover", capability="discovery", goal="scan",
        exit_artifacts=[], knowledge_refs=[], executor="claude_code",
        mode="discovery", depends_on=[],
    )]
    wf_id = _setup(tmp_path, nodes, node_defs)

    def fake_dispatch(node_def, root):
        return {"returncode": 0, "output": "scanned", "executor": "claude_code"}

    with patch("devforge.workflow.graph._engine._dispatch_discovery_node", side_effect=fake_dispatch):
        result = run_one_cycle(tmp_path)
    assert "discover" in result["dispatched"]
    manifest = read_manifest(tmp_path, wf_id)
    assert manifest["nodes"][0]["status"] == "completed"


def test_graph_discovery_node_failure(tmp_path: Path) -> None:
    """Discovery node failure is handled properly."""
    nodes = [_node("discover", mode="discovery")]
    node_defs = [NodeDefinition(
        id="discover", capability="discovery", goal="scan",
        exit_artifacts=[], knowledge_refs=[], executor="claude_code",
        mode="discovery", depends_on=[],
    )]
    wf_id = _setup(tmp_path, nodes, node_defs)

    def fake_dispatch(node_def, root):
        return {"returncode": 1, "output": "error occurred", "executor": "claude_code"}

    with patch("devforge.workflow.graph._engine._dispatch_discovery_node", side_effect=fake_dispatch):
        result = run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, wf_id)
    assert manifest["nodes"][0]["status"] == "failed"
    assert "error occurred" in (manifest["nodes"][0]["last_error"] or "")


def test_graph_discovery_node_max_attempts_fails_workflow(tmp_path: Path) -> None:
    """Discovery node exceeding MAX_ATTEMPTS fails the entire workflow."""
    nodes = [_node("discover", mode="discovery", attempt_count=2)]
    node_defs = [NodeDefinition(
        id="discover", capability="discovery", goal="scan",
        exit_artifacts=[], knowledge_refs=[], executor="claude_code",
        mode="discovery", depends_on=[],
    )]
    wf_id = _setup(tmp_path, nodes, node_defs)

    def fake_dispatch(node_def, root):
        return {"returncode": 1, "output": "failed again", "executor": "claude_code"}

    with patch("devforge.workflow.graph._engine._dispatch_discovery_node", side_effect=fake_dispatch):
        result = run_one_cycle(tmp_path)
    assert result["status"] == "workflow_failed"
