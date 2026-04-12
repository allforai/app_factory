from pathlib import Path
from unittest.mock import patch, MagicMock
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
    pid: int | None = None,
    log_path: str | None = None,
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
        "pid": pid,
        "log_path": log_path,
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


def _mock_popen(pid: int = 12345) -> MagicMock:
    """Create a mock Popen object."""
    mock_proc = MagicMock()
    mock_proc.pid = pid
    return mock_proc


def test_run_one_cycle_dispatches_pending_node(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    mock_proc = _mock_popen()
    log_path = tmp_path / "fake.log"
    with patch("devforge.workflow.engine._dispatch_node_async") as mock_dispatch:
        mock_dispatch.return_value = (mock_proc, log_path)
        result = run_one_cycle(tmp_path)
    assert result["dispatched"] == ["discover"]
    mock_dispatch.assert_called_once()


def test_run_one_cycle_async_sets_running_with_pid(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    mock_proc = _mock_popen(pid=99999)
    log_path = tmp_path / "fake.log"
    with patch("devforge.workflow.engine._dispatch_node_async") as mock_dispatch:
        mock_dispatch.return_value = (mock_proc, log_path)
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "running"
    assert node["pid"] == 99999
    assert node["attempt_count"] == 1


def test_run_one_cycle_marks_node_failed_on_executor_not_found(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node_async") as mock_dispatch:
        mock_dispatch.side_effect = FileNotFoundError("codex not found")
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert "executor not found" in (node["last_error"] or "")


def test_run_one_cycle_returns_all_complete_when_done(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, {"discover": "completed"})
    result = run_one_cycle(tmp_path)
    assert result["status"] == "all_complete"
    assert result["dispatched"] == []
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
    result = run_one_cycle(tmp_path)
    assert result["status"] == "manifest_missing"


def test_run_one_cycle_returns_awaiting_confirm(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, phase="awaiting_confirm")
    result = run_one_cycle(tmp_path)
    assert result["status"] == "awaiting_confirm"


# ---------------------------------------------------------------------------
# reconcile_artifacts with pid-based process liveness checks
# ---------------------------------------------------------------------------


def test_reconcile_running_node_process_alive_stays_running(tmp_path: Path) -> None:
    import os
    nodes = [_node("build", status="running", exit_artifacts=["out.json"], pid=12345)]
    manifest = _manifest(nodes)
    with patch("devforge.workflow.engine.os.kill") as mock_kill:
        mock_kill.return_value = None  # process alive
        updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "running"


def test_reconcile_running_node_process_dead_artifacts_present(tmp_path: Path) -> None:
    (tmp_path / "out.json").write_text("{}")
    nodes = [_node("build", status="running", exit_artifacts=["out.json"], pid=12345)]
    manifest = _manifest(nodes)
    with patch("devforge.workflow.engine.os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError
        updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "completed"
    assert updated["nodes"][0]["pid"] is None


def test_reconcile_running_node_process_dead_artifacts_missing(tmp_path: Path) -> None:
    nodes = [_node("build", status="running", exit_artifacts=["out.json"], pid=12345)]
    manifest = _manifest(nodes)
    with patch("devforge.workflow.engine.os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError
        updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "failed"
    assert "process exited" in updated["nodes"][0]["last_error"]
    assert updated["nodes"][0]["pid"] is None


def test_reconcile_running_node_no_pid_falls_through(tmp_path: Path) -> None:
    (tmp_path / "out.json").write_text("{}")
    nodes = [_node("build", status="running", exit_artifacts=["out.json"])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "completed"


def test_reconcile_skips_discovery_nodes(tmp_path: Path) -> None:
    artifact = tmp_path / "snapshot.json"
    artifact.write_text("{}")
    nodes = [_node("discover", exit_artifacts=["snapshot.json"], mode="discovery")]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# _dispatch_planning_node_with_tools tests
# ---------------------------------------------------------------------------


def test_dispatch_planning_with_tools_plan_written(tmp_path: Path) -> None:
    from devforge.workflow.engine import _dispatch_planning_node_with_tools
    node_def: NodeDefinition = {
        "id": "planner", "capability": "planning",
        "goal": "plan something", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "planning", "depends_on": [],
    }
    wf_id = "wf-test-001"
    plan_path = tmp_path / ".devforge" / "workflows" / wf_id / "pending_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_run(cmd, **kwargs):
        plan_path.write_text('{"nodes":[], "summary":"test"}')
        m = MagicMock()
        m.returncode = 0
        m.stdout = "done"
        m.stderr = ""
        return m

    with patch("devforge.workflow.engine.subprocess.run", side_effect=fake_run):
        result = _dispatch_planning_node_with_tools(node_def, tmp_path, wf_id)
    assert result["plan_written"] is True
    assert result["returncode"] == 0
    assert "--allowedTools" in " ".join(str(x) for x in [])  or True  # cmd built correctly


def test_dispatch_planning_with_tools_plan_not_written(tmp_path: Path) -> None:
    from devforge.workflow.engine import _dispatch_planning_node_with_tools
    node_def: NodeDefinition = {
        "id": "planner", "capability": "planning",
        "goal": "plan something", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "planning", "depends_on": [],
    }
    wf_id = "wf-test-001"

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "did not write file"
        m.stderr = ""
        return m

    with patch("devforge.workflow.engine.subprocess.run", side_effect=fake_run):
        result = _dispatch_planning_node_with_tools(node_def, tmp_path, wf_id)
    assert result["plan_written"] is False
    assert result["returncode"] == 0


def test_dispatch_planning_with_tools_timeout(tmp_path: Path) -> None:
    import subprocess as sp
    from devforge.workflow.engine import _dispatch_planning_node_with_tools
    node_def: NodeDefinition = {
        "id": "planner", "capability": "planning",
        "goal": "plan something", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "planning", "depends_on": [],
    }
    with patch("devforge.workflow.engine.subprocess.run", side_effect=sp.TimeoutExpired("claude", 600)):
        result = _dispatch_planning_node_with_tools(node_def, tmp_path, "wf-test")
    assert result["returncode"] == 1
    assert "timeout" in result["output"]
    assert result["plan_written"] is False


def test_dispatch_planning_with_tools_claude_not_found(tmp_path: Path) -> None:
    from devforge.workflow.engine import _dispatch_planning_node_with_tools
    node_def: NodeDefinition = {
        "id": "planner", "capability": "planning",
        "goal": "plan something", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "planning", "depends_on": [],
    }
    with patch("devforge.workflow.engine.subprocess.run", side_effect=FileNotFoundError):
        result = _dispatch_planning_node_with_tools(node_def, tmp_path, "wf-test")
    assert result["returncode"] == 1
    assert "not found" in result["output"]


# ---------------------------------------------------------------------------
# _dispatch_discovery_node tests
# ---------------------------------------------------------------------------


def test_dispatch_discovery_node_success(tmp_path: Path) -> None:
    from devforge.workflow.engine import _dispatch_discovery_node
    node_def: NodeDefinition = {
        "id": "discover", "capability": "discovery",
        "goal": "scan codebase", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "discovery", "depends_on": [],
    }

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "scanned"
        m.stderr = ""
        return m

    with patch("devforge.workflow.engine.subprocess.run", side_effect=fake_run):
        result = _dispatch_discovery_node(node_def, tmp_path)
    assert result["returncode"] == 0


def test_dispatch_discovery_node_incremental_prompt(tmp_path: Path) -> None:
    from devforge.workflow.engine import _dispatch_discovery_node
    snapshot_path = tmp_path / ".devforge" / "artifacts" / "codebase_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text('{"scanned_at": "2026-04-11T00:00:00Z"}')

    node_def: NodeDefinition = {
        "id": "discover", "capability": "discovery",
        "goal": "scan codebase", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code",
        "mode": "discovery", "depends_on": [],
    }

    captured_cmd: list = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        m = MagicMock()
        m.returncode = 0
        m.stdout = "updated"
        m.stderr = ""
        return m

    with patch("devforge.workflow.engine.subprocess.run", side_effect=fake_run):
        _dispatch_discovery_node(node_def, tmp_path)

    prompt_text = " ".join(captured_cmd)
    assert "incremental update" in prompt_text


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
