import json
from pathlib import Path

from devforge.executors import EXECUTOR_REGISTRY, get_executor_adapter
from devforge.graph import RuntimeState, concept_collection_node, graph_validation_node, planning_and_shaping_node, project_scheduler_node
from devforge.planning import apply_patch_operations
from devforge.roles import ROLE_REGISTRY, get_role_spec
from devforge.scheduler import select_workset
from devforge.state import ExecutorPolicy, SeamState, WorkPackage


def test_executor_policy_resolution_order() -> None:
    policy = ExecutorPolicy(
        policy_id="p1",
        default="claude_code",
        by_phase={"implementation": "codex"},
        by_role={"software_engineer": "cline"},
        by_domain={"frontend": "opencode"},
        by_work_package={"wp-1": "python"},
    )

    assert policy.resolve(work_package_id="wp-1", domain="frontend", role_id="software_engineer", phase="implementation") == "python"
    assert policy.resolve(work_package_id="wp-2", domain="frontend", role_id="software_engineer", phase="implementation") == "opencode"
    assert policy.resolve(work_package_id="wp-2", domain="backend", role_id="software_engineer", phase="implementation") == "cline"
    assert policy.resolve(work_package_id="wp-2", domain="backend", role_id="product_manager", phase="implementation") == "codex"
    assert policy.resolve(work_package_id="wp-2", domain="backend", role_id="product_manager", phase="acceptance") == "claude_code"


def test_role_registry_contains_core_roles() -> None:
    assert "software_engineer" in ROLE_REGISTRY
    assert "qa_engineer" in ROLE_REGISTRY
    assert get_role_spec("integration_owner").preferred_executors == ["python", "claude_code"]


def test_executor_registry_contains_core_adapters() -> None:
    assert "python" in EXECUTOR_REGISTRY
    assert "claude_code" in EXECUTOR_REGISTRY
    assert "codex" in EXECUTOR_REGISTRY
    assert get_executor_adapter("codex").supports_role("software_engineer") is True


def test_fixture_files_are_valid_json() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "src" / "devforge" / "fixtures"
    for name in ("game_project.json", "ecommerce_project.json"):
        data = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        assert "initiative" in data
        assert "projects" in data
        assert "work_packages" in data
        assert "seams" in data


def test_select_workset_respects_dependencies_and_frozen_seams() -> None:
    work_packages = [
        WorkPackage(
            work_package_id="wp-done",
            initiative_id="i1",
            project_id="p1",
            phase="implementation",
            domain="backend",
            role_id="software_engineer",
            title="done",
            goal="done",
            status="completed",
        ),
        WorkPackage(
            work_package_id="wp-ready",
            initiative_id="i1",
            project_id="p1",
            phase="implementation",
            domain="frontend",
            role_id="software_engineer",
            title="ready",
            goal="ready",
            status="ready",
            priority=90,
            depends_on=["wp-done"],
            related_seams=["s1"],
        ),
        WorkPackage(
            work_package_id="wp-blocked-seam",
            initiative_id="i1",
            project_id="p1",
            phase="implementation",
            domain="frontend",
            role_id="software_engineer",
            title="blocked seam",
            goal="blocked seam",
            status="ready",
            priority=100,
            related_seams=["s2"],
        ),
    ]
    seams = [
        SeamState(
            seam_id="s1",
            initiative_id="i1",
            source_project_id="p1",
            target_project_id="p2",
            type="api",
            name="ok",
            status="frozen",
            contract_version="v1",
            owner_role_id="integration_owner",
            owner_executor="claude_code",
        ),
        SeamState(
            seam_id="s2",
            initiative_id="i1",
            source_project_id="p1",
            target_project_id="p2",
            type="api",
            name="not frozen",
            status="draft",
            contract_version="v1",
            owner_role_id="integration_owner",
            owner_executor="claude_code",
        ),
    ]

    selected = select_workset(work_packages, seams, limit=2)
    assert [wp.work_package_id for wp in selected] == ["wp-ready"]


def test_apply_patch_operations_supports_add_replace_append_unique() -> None:
    snapshot = {"projects": [{"id": "p1"}], "queue": ["a"]}
    updated = apply_patch_operations(
        snapshot,
        [
            {"action": "add", "target": "projects", "value": {"id": "p2"}},
            {"action": "append_unique", "target": "queue", "value": "b"},
            {"action": "replace", "target": "active_project", "value": "p2"},
        ],
    )
    assert updated["projects"] == [{"id": "p1"}, {"id": "p2"}]
    assert updated["queue"] == ["a", "b"]
    assert updated["active_project"] == "p2"


def test_minimal_graph_nodes_update_runtime_state() -> None:
    state = RuntimeState(workspace_id="w1", foreground_project="p1")
    state = project_scheduler_node(state)
    assert state.active_project_id == "p1"

    state = concept_collection_node(
        state,
        project={"name": "Demo", "current_phase": "concept_collect", "project_archetype": "ecommerce"},
        knowledge_ids=["domain.ecommerce", "phase.concept_collect"],
        specialized_knowledge={"focus": ["ecommerce", "concept_collect"]},
    )
    assert state.concept_decision["source"] == "mock:mock-structured-v1"
    assert state.phase_goal == "collect concept model for Demo"

    state = planning_and_shaping_node(
        state,
        ["wp-1"],
        project={"name": "Demo", "current_phase": "implementation"},
        node_knowledge_packet={"brief": "implement demo", "focus": {"phase": "implementation"}},
    )
    assert state.current_workset == ["wp-1"]
    assert state.planning_decision["source"] == "mock:mock-structured-v1"

    state = graph_validation_node(state)
    assert state.replan_reason is None

    empty_state = RuntimeState(workspace_id="w1")
    empty_state = graph_validation_node(empty_state)
    assert empty_state.replan_reason == "no_runnable_work"
