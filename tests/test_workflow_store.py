import json
from pathlib import Path
from devforge.workflow.models import (
    WorkflowIndex,
    WorkflowIntent,
    WorkflowManifest,
    NodeDefinition,
    PullContextEvent,
    TransitionEntry,
)
from devforge.workflow.store import (
    append_pull_event,
    read_index,
    write_index,
    read_manifest,
    write_manifest,
    read_node,
    write_node,
    append_transition,
    read_pull_events,
    read_current_intent,
    read_transitions,
    active_workflow_id,
    write_current_intent,
)


def _make_index(wf_id: str = "wf-test-001") -> WorkflowIndex:
    return {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [
            {"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}
        ],
    }


def _make_manifest(wf_id: str = "wf-test-001") -> WorkflowManifest:
    return {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": "running",
        "nodes": [
            {
                "id": "discover",
                "status": "pending",
                "depends_on": [],
                "exit_artifacts": [".devforge/artifacts/summary.json"],
                "executor": "codex",
                "mode": None,
                "parent_node_id": None,
                "depth": 0,
                "attempt_count": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
                "pid": None,
                "log_path": None,
                "epoch": {"epoch_count": 0, "failure_history": [], "last_failure_at": None},
            }
        ],
    }


def test_index_round_trip(tmp_path: Path) -> None:
    index = _make_index()
    write_index(tmp_path, index)
    assert read_index(tmp_path) == index


def test_read_index_returns_empty_when_missing(tmp_path: Path) -> None:
    result = read_index(tmp_path)
    assert result["schema_version"] == "1.0"
    assert result["active_workflow_id"] is None
    assert result["workflows"] == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = _make_manifest()
    write_manifest(tmp_path, "wf-test-001", manifest)
    assert read_manifest(tmp_path, "wf-test-001") == manifest


def test_node_round_trip(tmp_path: Path) -> None:
    node: NodeDefinition = {
        "id": "discover",
        "capability": "discovery",
        "goal": "Scan the repo",
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
    }
    write_node(tmp_path, "wf-test-001", node)
    assert read_node(tmp_path, "wf-test-001", "discover") == node


def test_current_intent_round_trip(tmp_path: Path) -> None:
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    intent: WorkflowIntent = {
        "goal": "Updated mission",
        "updated_at": "2026-04-13T00:00:00Z",
        "updated_by": "diagnose-node",
        "lessons_learned": ["Need to prioritize recovery flow."],
    }
    write_current_intent(tmp_path, "wf-test-001", intent)
    assert read_current_intent(tmp_path, "wf-test-001") == intent


def test_current_intent_falls_back_to_manifest_goal(tmp_path: Path) -> None:
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    intent = read_current_intent(tmp_path, "wf-test-001")
    assert intent["goal"] == "Test workflow"
    assert intent["updated_by"] == "manifest-fallback"


def test_append_transition_creates_jsonl(tmp_path: Path) -> None:
    entry: TransitionEntry = {
        "node": "discover",
        "status": "completed",
        "started_at": "2026-04-11T00:00:00Z",
        "completed_at": "2026-04-11T00:01:00Z",
        "artifacts_created": [".devforge/artifacts/summary.json"],
        "error": None,
    }
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    append_transition(tmp_path, "wf-test-001", entry)
    append_transition(tmp_path, "wf-test-001", entry)
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 2
    assert transitions[0]["node"] == "discover"


def test_read_transitions_skips_corrupted_lines(tmp_path: Path) -> None:
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    # Write one valid + one corrupted line directly
    transitions_path = tmp_path / ".devforge" / "workflows" / "wf-test-001" / "transitions.jsonl"
    transitions_path.parent.mkdir(parents=True, exist_ok=True)
    transitions_path.write_text(
        '{"node": "a", "status": "completed", "started_at": "t", "completed_at": "t", "artifacts_created": [], "error": null}\n'
        'NOT VALID JSON {{{\n',
        encoding="utf-8",
    )
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 1
    assert transitions[0]["node"] == "a"


def test_write_index_is_atomic(tmp_path: Path) -> None:
    # write_index should not leave partial files; verify the file is complete after write
    index = _make_index()
    write_index(tmp_path, index)
    index_path = tmp_path / ".devforge" / "workflows" / "index.json"
    content = json.loads(index_path.read_text())
    assert content["schema_version"] == "1.0"


def test_active_workflow_id_returns_none_when_missing(tmp_path: Path) -> None:
    assert active_workflow_id(tmp_path) is None


def test_active_workflow_id_returns_value(tmp_path: Path) -> None:
    write_index(tmp_path, _make_index("wf-abc"))
    assert active_workflow_id(tmp_path) == "wf-abc"


def test_append_pull_event_creates_jsonl(tmp_path: Path) -> None:
    entry: PullContextEvent = {
        "event_id": "pull-1",
        "node_id": "discover",
        "path": "src/app.py",
        "kind": "text",
        "bytes_read": 42,
        "created_at": "2026-04-13T00:00:00Z",
    }
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    append_pull_event(tmp_path, "wf-test-001", entry)
    append_pull_event(tmp_path, "wf-test-001", entry)
    events = read_pull_events(tmp_path, "wf-test-001")
    assert len(events) == 2
    assert events[0]["path"] == "src/app.py"
