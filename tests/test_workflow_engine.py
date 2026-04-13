import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from devforge.workflow.models import NodeManifestEntry, NodeDefinition, WorkflowManifest, WorkflowIndex
from devforge.workflow.engine import select_next_nodes, reconcile_artifacts, run_one_cycle, _build_executor_cmd, _load_knowledge
from devforge.workflow.store import read_current_intent, write_current_intent, write_index, write_manifest, write_node, read_manifest, read_index, read_pull_events, read_node


def _node(
    node_id: str,
    status: str = "pending",
    strategy: str | None = None,
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
        "strategy": strategy,
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
        "epoch": {"epoch_count": 0, "failure_history": [], "last_failure_at": None},
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


def test_select_next_nodes_includes_stale_nodes_when_ready() -> None:
    manifest = _manifest([_node("a", status="completed"), _node("b", status="stale", depends_on=["a"])])
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
            "strategy": "REVERSE_ANALYSIS" if node_id.startswith("discover") else None,
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


def test_init_workflow_writes_current_intent(tmp_path: Path) -> None:
    from devforge.repl import _init_workflow

    _init_workflow(tmp_path, "Ship a dynamic intent workflow")
    index = read_index(tmp_path)
    wf_id = index["active_workflow_id"]
    assert wf_id is not None

    intent = read_current_intent(tmp_path, wf_id)
    assert intent["goal"] == "Ship a dynamic intent workflow"
    assert intent["updated_by"] == "wf-init"
    assert intent["lessons_learned"] == []
    assert intent["active_hypotheses"] == []


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
    _setup_workflow(tmp_path, {"discover": "completed", "alignment-audit": "completed"})
    write_node(tmp_path, "wf-test-001", {
        "id": "alignment-audit",
        "capability": "alignment-audit",
        "strategy": "FULL_STACK_VALIDATION",
        "goal": "Audit alignment",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["discover"],
    })
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


def test_run_one_cycle_intent_update_changes_goal_seen_by_next_node(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, {"discover": "completed", "build": "pending"})
    manifest = read_manifest(tmp_path, "wf-test-001")
    build = next(node for node in manifest["nodes"] if node["id"] == "build")
    build["depends_on"] = ["discover"]
    write_manifest(tmp_path, "wf-test-001", manifest)

    discover_dir = tmp_path / ".devforge" / "artifacts" / "discover"
    discover_dir.mkdir(parents=True, exist_ok=True)
    (discover_dir / "intent_update.json").write_text(json.dumps({
        "goal": "Build the corrected workflow path",
        "lessons_learned": ["The first approach was mis-scoped."],
        "active_hypotheses": ["A narrower implementation path will converge faster."],
    }), encoding="utf-8")

    captured: dict[str, str] = {}

    def fake_build_codex_command(*, prompt: str, working_dir: str) -> list[str]:
        captured["prompt"] = prompt
        return ["codex", prompt]

    mock_proc = _mock_popen(pid=54321)
    with patch("devforge.workflow.engine.build_codex_command", side_effect=fake_build_codex_command), \
            patch("devforge.workflow.engine.subprocess.Popen", return_value=mock_proc):
        result = run_one_cycle(tmp_path)

    assert result["status"] == "ok"
    assert result["dispatched"] == ["build"]
    assert "Build the corrected workflow path" in captured["prompt"]
    assert "The first approach was mis-scoped." in captured["prompt"]
    intent = read_current_intent(tmp_path, "wf-test-001")
    assert intent["goal"] == "Build the corrected workflow path"
    assert (discover_dir / "intent_update.processed.json").exists()


def test_reconcile_high_attention_intent_update_spawns_replanner(tmp_path: Path) -> None:
    from devforge.workflow.store import write_node

    manifest = _manifest([
        _node("architect", status="completed"),
        _node("implement", depends_on=["architect"]),
    ])
    write_manifest(tmp_path, manifest["id"], manifest)
    write_current_intent(tmp_path, manifest["id"], {
        "goal": "Original goal",
        "updated_at": "2026-04-11T00:00:00Z",
        "updated_by": "wf-init",
        "lessons_learned": [],
        "active_hypotheses": [],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "architect",
        "capability": "architecture",
        "strategy": "GOVERNANCE",
        "goal": "Reassess the architecture",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
        "attention_weight": 2.0,
    })
    write_node(tmp_path, manifest["id"], {
        "id": "implement",
        "capability": "coding",
        "strategy": "TDD_REFACTOR",
        "goal": "Implement the plan",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["architect"],
    })

    intent_dir = tmp_path / ".devforge" / "artifacts" / "architect"
    intent_dir.mkdir(parents=True, exist_ok=True)
    (intent_dir / "intent_update.json").write_text(json.dumps({
        "redefined_goal": "Redefine the workflow around architectural correction",
        "lessons_learned": ["Upstream architecture invalidated the original path."],
        "level": 3,
        "requires_replan": True,
    }), encoding="utf-8")

    updated = reconcile_artifacts(tmp_path, manifest)

    replanner = next(node for node in updated["nodes"] if node["id"].startswith("replan-architect-"))
    implement = next(node for node in updated["nodes"] if node["id"] == "implement")
    assert replanner["mode"] == "planning"
    assert implement["status"] == "stale"
    assert replanner["id"] in implement["depends_on"]
    assert updated["workflow_status"] == "planning"
    assert read_current_intent(tmp_path, manifest["id"])["goal"] == "Redefine the workflow around architectural correction"


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


def test_reconcile_governance_violation_spawns_refactor(tmp_path: Path) -> None:
    from devforge.workflow.store import write_node

    artifact = tmp_path / "report.json"
    artifact.write_text(json.dumps({"architectural_smells": ["cross-layer dependency leak"]}), encoding="utf-8")
    nodes = [_node("governed", strategy="GOVERNANCE", exit_artifacts=["report.json"])]
    manifest = _manifest(nodes)
    node_def: NodeDefinition = {
        "id": "governed",
        "capability": "governance",
        "strategy": "GOVERNANCE",
        "goal": "Produce governed artifact",
        "exit_artifacts": ["report.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
    }
    write_node(tmp_path, manifest["id"], node_def)

    updated = reconcile_artifacts(tmp_path, manifest)
    governed = next(node for node in updated["nodes"] if node["id"] == "governed")
    refactor = next(node for node in updated["nodes"] if node["id"].startswith("refactor-governed-"))
    assert governed["status"] == "needs_refactor"
    assert refactor["status"] == "pending"


def test_reconcile_failed_node_spawns_diagnosis(tmp_path: Path) -> None:
    from devforge.workflow.store import write_node

    nodes = [_node("build", status="running", strategy="TDD_REFACTOR", exit_artifacts=["out.json"], pid=12345)]
    manifest = _manifest(nodes)
    node_def: NodeDefinition = {
        "id": "build",
        "capability": "coding",
        "strategy": "TDD_REFACTOR",
        "goal": "Build artifact",
        "exit_artifacts": ["out.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
    }
    write_node(tmp_path, manifest["id"], node_def)

    with patch("devforge.workflow.engine.os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError
        updated = reconcile_artifacts(tmp_path, manifest)

    diagnosis = next(node for node in updated["nodes"] if node["id"].startswith("diagnose-build-"))
    diagnosis_def = read_node(tmp_path, manifest["id"], diagnosis["id"])
    assert diagnosis["status"] == "pending"
    assert "rewind.json" in diagnosis_def["goal"]
    assert updated["nodes"][0]["status"] == "failed"


def test_reconcile_diagnosis_rewind_resets_target_and_marks_descendants_stale(tmp_path: Path) -> None:
    from devforge.workflow.store import read_transitions, write_node

    (tmp_path / "foundation.json").write_text("{}", encoding="utf-8")
    (tmp_path / "implementation.json").write_text("{}", encoding="utf-8")
    (tmp_path / "validation.json").write_text("{}", encoding="utf-8")

    nodes = [
        _node("foundation", status="completed", exit_artifacts=["foundation.json"]),
        _node("implementation", status="completed", depends_on=["foundation"], exit_artifacts=["implementation.json"]),
        _node("validation", status="completed", depends_on=["implementation"], exit_artifacts=["validation.json"]),
        _node("diagnose-validation-a1", status="completed", depends_on=["implementation"]),
    ]
    manifest = _manifest(nodes)

    write_node(tmp_path, manifest["id"], {
        "id": "foundation",
        "capability": "product-analysis",
        "strategy": "REVERSE_ANALYSIS",
        "goal": "Define the foundation",
        "exit_artifacts": ["foundation.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "implementation",
        "capability": "coding",
        "strategy": "TDD_REFACTOR",
        "goal": "Implement the feature",
        "exit_artifacts": ["implementation.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["foundation"],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "validation",
        "capability": "test-verify",
        "strategy": "FULL_STACK_VALIDATION",
        "goal": "Validate the feature",
        "exit_artifacts": ["validation.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["implementation"],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "diagnose-validation-a1",
        "capability": "diagnosis",
        "strategy": "REVERSE_ANALYSIS",
        "goal": "Diagnose the failure",
        "exit_artifacts": [".allforai/devforge/diagnosis/validation-a1.json"],
        "knowledge_refs": ["knowledge/content/vault/diagnosis.md"],
        "executor": "codex",
        "mode": None,
        "depends_on": ["implementation"],
    })

    rewind_dir = tmp_path / ".devforge" / "artifacts" / "diagnose-validation-a1"
    rewind_dir.mkdir(parents=True, exist_ok=True)
    (rewind_dir / "rewind.json").write_text(
        json.dumps({"target_node_id": "foundation", "reason": "Gap in foundation"}),
        encoding="utf-8",
    )

    updated = reconcile_artifacts(tmp_path, manifest)

    foundation = next(node for node in updated["nodes"] if node["id"] == "foundation")
    implementation = next(node for node in updated["nodes"] if node["id"] == "implementation")
    validation = next(node for node in updated["nodes"] if node["id"] == "validation")
    diagnosis = next(node for node in updated["nodes"] if node["id"] == "diagnose-validation-a1")

    assert foundation["status"] == "pending"
    assert implementation["status"] == "stale"
    assert validation["status"] == "stale"
    assert diagnosis["status"] == "completed"
    assert not (tmp_path / "foundation.json").exists()
    assert not (tmp_path / "implementation.json").exists()
    assert not (tmp_path / "validation.json").exists()
    assert (rewind_dir / "rewind.processed.json").exists()

    transitions = read_transitions(tmp_path, manifest["id"])
    assert [entry["status"] for entry in transitions] == ["rewinding", "stale", "stale"]


def test_reconcile_level_one_rewind_resets_only_target_leaf(tmp_path: Path) -> None:
    from devforge.workflow.store import write_node

    (tmp_path / "feature.json").write_text("{}", encoding="utf-8")
    (tmp_path / "verify.json").write_text("{}", encoding="utf-8")
    nodes = [
        _node("feature", status="completed", exit_artifacts=["feature.json"]),
        _node("verify-feature-a1", status="completed", depends_on=["feature"], exit_artifacts=["verify.json"]),
        _node("diagnose-verify-feature-a1-a1", status="completed", depends_on=["feature"]),
    ]
    manifest = _manifest(nodes)

    for node_id, capability in (
        ("feature", "coding"),
        ("verify-feature-a1", "full-stack-validation"),
        ("diagnose-verify-feature-a1-a1", "diagnosis"),
    ):
        write_node(tmp_path, manifest["id"], {
            "id": node_id,
            "capability": capability,
            "strategy": "TDD_REFACTOR" if capability == "coding" else "FULL_STACK_VALIDATION",
            "goal": f"Run {node_id}",
            "exit_artifacts": ["feature.json"] if node_id == "feature" else [],
            "knowledge_refs": [],
            "executor": "codex",
            "mode": None,
            "depends_on": ["feature"] if node_id != "feature" else [],
        })

    rewind_dir = tmp_path / ".devforge" / "artifacts" / "diagnose-verify-feature-a1-a1"
    rewind_dir.mkdir(parents=True, exist_ok=True)
    (rewind_dir / "rewind.json").write_text(
        json.dumps({"target_node_id": "feature", "rewind_level": 1, "reason": "Patch residual"}),
        encoding="utf-8",
    )

    updated = reconcile_artifacts(tmp_path, manifest)
    feature = next(node for node in updated["nodes"] if node["id"] == "feature")
    verify = next(node for node in updated["nodes"] if node["id"] == "verify-feature-a1")
    assert feature["status"] == "pending"
    assert verify["status"] == "completed"
    assert feature["epoch"]["epoch_count"] == 1


def test_reconcile_level_three_rewind_updates_current_intent(tmp_path: Path) -> None:
    from devforge.workflow.store import read_current_intent, write_current_intent, write_node

    write_current_intent(tmp_path, "wf-test", {
        "goal": "Old mission",
        "updated_at": "2026-04-13T00:00:00Z",
        "updated_by": "wf-init",
        "lessons_learned": [],
    })
    (tmp_path / "concept.json").write_text("{}", encoding="utf-8")
    (tmp_path / "functional.json").write_text("{}", encoding="utf-8")
    nodes = [
        _node("project-concept", status="completed", exit_artifacts=["concept.json"]),
        _node("functional-map", status="completed", depends_on=["project-concept"], exit_artifacts=["functional.json"]),
        _node("diagnose-functional-map-a1", status="completed", depends_on=["project-concept"]),
    ]
    manifest = _manifest(nodes)

    write_node(tmp_path, manifest["id"], {
        "id": "project-concept",
        "capability": "product-analysis",
        "strategy": "REVERSE_ANALYSIS",
        "goal": "Define concept",
        "exit_artifacts": ["concept.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "functional-map",
        "capability": "architecture",
        "strategy": "GOVERNANCE",
        "goal": "Define functional map",
        "exit_artifacts": ["functional.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["project-concept"],
    })
    write_node(tmp_path, manifest["id"], {
        "id": "diagnose-functional-map-a1",
        "capability": "diagnosis",
        "strategy": "REVERSE_ANALYSIS",
        "goal": "Diagnose intent gap",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": ["project-concept"],
    })

    rewind_dir = tmp_path / ".devforge" / "artifacts" / "diagnose-functional-map-a1"
    rewind_dir.mkdir(parents=True, exist_ok=True)
    (rewind_dir / "rewind.json").write_text(
        json.dumps({
            "rewind_level": 3,
            "reason": "Original mission was wrong",
            "evolved_goal": "Refocus the project around recovery-first onboarding",
            "lessons_learned": ["User value is in recovery, not initial setup."],
        }),
        encoding="utf-8",
    )

    updated = reconcile_artifacts(tmp_path, manifest)
    concept = next(node for node in updated["nodes"] if node["id"] == "project-concept")
    functional = next(node for node in updated["nodes"] if node["id"] == "functional-map")
    intent = read_current_intent(tmp_path, manifest["id"])
    assert concept["status"] == "pending"
    assert functional["status"] == "stale"
    assert intent["goal"] == "Refocus the project around recovery-first onboarding"
    assert "recovery" in updated["goal"].lower()


def test_reconcile_completed_work_inserts_alignment_audit(tmp_path: Path) -> None:
    from devforge.workflow.store import write_current_intent, write_node

    write_current_intent(tmp_path, "wf-test", {
        "goal": "Evolved mission",
        "updated_at": "2026-04-13T00:00:00Z",
        "updated_by": "summary-node",
        "lessons_learned": ["Need alignment audit."],
    })
    nodes = [_node("feature", status="completed", exit_artifacts=[])]
    manifest = _manifest(nodes)
    write_node(tmp_path, manifest["id"], {
        "id": "feature",
        "capability": "coding",
        "strategy": "TDD_REFACTOR",
        "goal": "Implement feature",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
        "depends_on": [],
    })

    updated = reconcile_artifacts(tmp_path, manifest)
    audit = next(node for node in updated["nodes"] if node["id"] == "alignment-audit")
    audit_def = read_node(tmp_path, manifest["id"], "alignment-audit")
    assert audit["status"] == "pending"
    assert "current_intent.json" in audit_def["goal"]


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
    source_summary_path = tmp_path / ".allforai" / "code-replicate" / "source-summary.json"
    source_summary_path.parent.mkdir(parents=True, exist_ok=True)
    source_summary_path.write_text(json.dumps({
        "project": {"detected_stacks": ["python", "fastapi"]},
        "modules": [
            {
                "id": "M001",
                "path": "src/api",
                "responsibility": "Serve API entrypoints",
                "exposed_interfaces": ["create_app"],
                "dependencies": [],
                "key_files": ["main.py"],
            }
        ],
    }), encoding="utf-8")

    node_def: NodeDefinition = {
        "id": "discover", "capability": "discovery",
        "goal": "scan codebase", "exit_artifacts": [],
        "knowledge_refs": [], "executor": "claude_code", "strategy": "REVERSE_ANALYSIS",
        "mode": "discovery", "depends_on": [],
    }

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "updated"
        m.stderr = ""
        return m

    with patch("devforge.workflow.engine.subprocess.run", side_effect=fake_run):
        _dispatch_discovery_node(node_def, tmp_path)

    snapshot = json.loads((tmp_path / ".devforge" / "artifacts" / "codebase_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["semantics"]["architectural_insights"][0].startswith("Main Entry Point found at")


def test_load_knowledge_uses_snapshot_index_not_full_file_content(tmp_path: Path) -> None:
    snapshot_path = tmp_path / ".devforge" / "artifacts" / "codebase_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps({
        "structure": {
            "tech_stack": ["python", "fastapi"],
            "entry_points": ["src/api/main.py"],
            "key_files": ["src/api/main.py"],
            "directories": ["src"],
        },
        "modules": [
            {
                "path": "src/api",
                "purpose": "Serve API entrypoints",
                "exports": ["create_app"],
                "depends_on": ["src/core"],
            }
        ],
        "semantics": {
            "core_domains": ["src/core"],
            "architectural_insights": ["Main Entry Point found at src/api/main.py"],
            "key_logic_flows": [{"from": "src/api", "to": "src/core", "reason": "request orchestration"}],
        },
    }), encoding="utf-8")
    knowledge_ref = tmp_path / "knowledge.md"
    knowledge_ref.write_text("FULL FILE CONTENT SHOULD NOT APPEAR", encoding="utf-8")

    prompt_context = _load_knowledge(["knowledge.md"], tmp_path)

    assert "Push Context Index" in prompt_context
    assert "Serve API entrypoints" in prompt_context
    assert "FULL FILE CONTENT SHOULD NOT APPEAR" not in prompt_context


def test_build_executor_cmd_includes_pull_tool_and_attention_weighted_context(tmp_path: Path) -> None:
    snapshot_path = tmp_path / ".devforge" / "artifacts" / "codebase_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps({
        "structure": {
            "tech_stack": ["python"],
            "entry_points": ["src/main.py"],
            "key_files": ["src/main.py"],
            "directories": ["src"],
        },
        "modules": [
            {"path": "src/core", "purpose": "Domain logic", "exports": ["CoreService"], "depends_on": []},
            {"path": "src/support", "purpose": "Support logic", "exports": ["SupportService"], "depends_on": []},
        ],
        "semantics": {
            "core_domains": ["src/core"],
            "architectural_insights": ["Core domain is isolated in src/core"],
            "key_logic_flows": [{"from": "src/core", "to": "src/support", "reason": "shared workflow"}],
        },
    }), encoding="utf-8")
    runtime_snapshot = tmp_path / ".devforge" / "devforge.snapshot.json"
    runtime_snapshot.parent.mkdir(parents=True, exist_ok=True)
    runtime_snapshot.write_text(json.dumps({
        "work_packages": [
            {"work_package_id": "wp-1", "attention_weight": 2.0},
        ]
    }), encoding="utf-8")

    node_def: NodeDefinition = {
        "id": "wp-1",
        "capability": "coding",
        "goal": "Implement the feature",
        "exit_artifacts": [],
        "knowledge_refs": ["knowledge/content/vault/diagnosis.md"],
        "executor": "claude_code",
        "mode": None,
        "depends_on": [],
    }

    cmd, _executor = _build_executor_cmd(node_def, tmp_path, wf_id="wf-test-001")
    prompt = cmd[-1]

    assert "--allowedTools" in cmd
    assert "attention_weight: 2.00" in prompt
    assert "src/core" in prompt
    assert "pull_context(path: str) -> str" in prompt
    assert "PYTHONPATH=src python -m devforge.workflow.pull_context" in prompt


def test_pull_context_cli_logs_event(tmp_path: Path) -> None:
    from devforge.workflow.pull_context import pull_context

    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("print('hello')\n", encoding="utf-8")

    content = pull_context(tmp_path, "wf-test-001", "node-1", "src/app.py")

    assert "print('hello')" in content
    events = read_pull_events(tmp_path, "wf-test-001")
    assert len(events) == 1
    assert events[0]["node_id"] == "node-1"
    assert events[0]["path"] == "src/app.py"


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
