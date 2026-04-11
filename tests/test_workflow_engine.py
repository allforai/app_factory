from pathlib import Path
from unittest.mock import patch
from devforge.workflow.models import NodeManifestEntry, NodeDefinition, WorkflowManifest, WorkflowIndex
from devforge.workflow.engine import select_next_nodes, reconcile_artifacts, run_one_cycle
from devforge.workflow.store import write_index, write_manifest, write_node, read_manifest, read_index


def _node(
    node_id: str,
    status: str = "pending",
    depends_on: list[str] | None = None,
    exit_artifacts: list[str] | None = None,
    mode: str | None = None,
    attempt_count: int = 0,
) -> NodeManifestEntry:
    return {
        "id": node_id,
        "status": status,  # type: ignore[typeddict-item]
        "depends_on": depends_on or [],
        "exit_artifacts": exit_artifacts or [],
        "executor": "codex",
        "mode": mode,
        "parent_node_id": None,
        "depth": 0,
        "attempt_count": attempt_count,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
    }


def _manifest(nodes: list[NodeManifestEntry], phase: str = "running") -> WorkflowManifest:
    return {
        "id": "wf-test",
        "goal": "test",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": phase,  # type: ignore[typeddict-item]
        "nodes": nodes,
    }


def test_select_next_nodes_no_deps() -> None:
    manifest = _manifest([_node("a"), _node("b")])
    result = select_next_nodes(manifest)
    assert {n["id"] for n in result} == {"a", "b"}


def test_select_next_nodes_respects_deps() -> None:
    manifest = _manifest([_node("a"), _node("b", depends_on=["a"])])
    result = select_next_nodes(manifest)
    assert [n["id"] for n in result] == ["a"]


def test_select_next_nodes_dep_completed() -> None:
    manifest = _manifest([_node("a", status="completed"), _node("b", depends_on=["a"])])
    result = select_next_nodes(manifest)
    assert [n["id"] for n in result] == ["b"]


def test_select_next_nodes_max_concurrent() -> None:
    nodes = [_node(f"n{i}") for i in range(5)]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert len(result) == 3  # MAX_CONCURRENT = 3


def test_select_next_nodes_running_counts_toward_limit() -> None:
    nodes = [_node("a", status="running"), _node("b"), _node("c"), _node("d")]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert len(result) == 2  # 1 running + 2 new = 3 total


def test_select_next_nodes_empty_when_all_running() -> None:
    nodes = [_node(f"n{i}", status="running") for i in range(3)]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert result == []


def test_reconcile_artifacts_marks_completed(tmp_path: Path) -> None:
    artifact = tmp_path / "summary.json"
    artifact.write_text("{}")
    nodes = [_node("discover", exit_artifacts=["summary.json"])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "completed"


def test_reconcile_artifacts_leaves_pending_when_missing(tmp_path: Path) -> None:
    nodes = [_node("discover", exit_artifacts=["missing.json"])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


def test_reconcile_artifacts_no_artifacts_stays_pending(tmp_path: Path) -> None:
    nodes = [_node("discover", exit_artifacts=[])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


def test_reconcile_skips_planning_nodes(tmp_path: Path) -> None:
    # Planning nodes never reconcile via artifacts even if files exist
    artifact = tmp_path / "plan.json"
    artifact.write_text("{}")
    nodes = [_node("planner", exit_artifacts=["plan.json"], mode="planning")]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# run_one_cycle tests (Task 6)
# ---------------------------------------------------------------------------


def _setup_workflow(
    tmp_path: Path,
    nodes_status: dict[str, str] | None = None,
    phase: str = "running",
    attempt_counts: dict[str, int] | None = None,
) -> None:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)

    nodes_status = nodes_status or {"discover": "pending"}
    attempt_counts = attempt_counts or {}
    manifest_nodes: list[NodeManifestEntry] = []
    for node_id, status in nodes_status.items():
        manifest_nodes.append(_node(
            node_id,
            status=status,
            attempt_count=attempt_counts.get(node_id, 0),
        ))
    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": phase,  # type: ignore[typeddict-item]
        "nodes": manifest_nodes,
    }
    write_manifest(tmp_path, wf_id, manifest)

    for node_id in nodes_status:
        node_def: NodeDefinition = {
            "id": node_id,
            "capability": "discovery",
            "goal": f"Run {node_id}",
            "exit_artifacts": [],
            "knowledge_refs": [],
            "executor": "codex",
            "mode": None,
            "depends_on": [],
        }
        write_node(tmp_path, wf_id, node_def)


def test_run_one_cycle_dispatches_pending_node(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        result = run_one_cycle(tmp_path)
    assert result["dispatched"] == ["discover"]
    mock_dispatch.assert_called_once()


def test_run_one_cycle_marks_node_completed_on_success(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "completed"
    assert node["attempt_count"] == 1
    assert node["last_completed_at"] is not None
    assert node["last_error"] is None


def test_run_one_cycle_marks_node_failed_on_error(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 1, "output": "error msg", "executor": "codex"}
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert node["last_error"] == "error msg"
    assert node["attempt_count"] == 1


def test_run_one_cycle_writes_transition_log(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        run_one_cycle(tmp_path)
    from devforge.workflow.store import read_transitions
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 1
    assert transitions[0]["node"] == "discover"
    assert transitions[0]["status"] == "completed"


def test_run_one_cycle_returns_all_complete_when_done(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, {"discover": "completed"})
    result = run_one_cycle(tmp_path)
    assert result["status"] == "all_complete"
    assert result["dispatched"] == []
    # index.status should be synced to "complete"
    index = read_index(tmp_path)
    assert index["workflows"][0]["status"] == "complete"


def test_run_one_cycle_returns_no_active_workflow_when_missing(tmp_path: Path) -> None:
    result = run_one_cycle(tmp_path)
    assert result["status"] == "no_active_workflow"


def test_run_one_cycle_returns_manifest_missing(tmp_path: Path) -> None:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)
    # manifest file is NOT written
    result = run_one_cycle(tmp_path)
    assert result["status"] == "manifest_missing"


def test_run_one_cycle_returns_awaiting_confirm(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, phase="awaiting_confirm")
    result = run_one_cycle(tmp_path)
    assert result["status"] == "awaiting_confirm"


def test_run_one_cycle_executor_not_found(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.side_effect = FileNotFoundError("codex not found")
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert "executor not found" in (node["last_error"] or "")


def test_run_one_cycle_executor_timeout(tmp_path: Path) -> None:
    import subprocess as _subprocess
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.side_effect = _subprocess.TimeoutExpired(cmd="codex", timeout=300)
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert "timeout" in (node["last_error"] or "")


def test_run_one_cycle_workflow_fails_after_max_attempts(tmp_path: Path) -> None:
    # attempt_count already at 2, so this attempt makes it 3 → workflow_status = failed
    _setup_workflow(tmp_path, attempt_counts={"discover": 2})
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 1, "output": "still failing", "executor": "codex"}
        result = run_one_cycle(tmp_path)
    assert result["status"] == "workflow_failed"
    manifest = read_manifest(tmp_path, "wf-test-001")
    assert manifest["workflow_status"] == "failed"
    index = read_index(tmp_path)
    assert index["workflows"][0]["status"] == "failed"


from devforge.session import UserIntent


def test_user_intent_accepts_wf_kinds() -> None:
    intents = [
        UserIntent(kind="show_workflow"),
        UserIntent(kind="run_workflow"),
        UserIntent(kind="init_workflow"),
        UserIntent(kind="confirm_workflow"),
        UserIntent(kind="log_workflow"),
        UserIntent(kind="reset_workflow_node", payload={"node_id": "discover"}),
        UserIntent(kind="list_workflows"),
        UserIntent(kind="switch_workflow", payload={"wf_id": "wf-test-001"}),
    ]
    assert all(i.kind.endswith("workflow") or "workflow" in i.kind for i in intents)
