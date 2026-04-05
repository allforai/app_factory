from devforge.graph import build_meta_graph
from devforge.graph.builder import _apply_executor_result, run_cycle
from devforge.graph.transitions import next_step_for_state
from devforge.graph.runtime_state import RuntimeState
from devforge.main import run_fixture_cycle
from unittest.mock import patch
from devforge.persistence import (
    FileArtifactStore,
    JsonMemoryStore,
    JsonStore,
    JsonlEventStore,
    WorkspacePersistence,
    build_local_workspace_persistence,
)


def test_next_step_for_state_prefers_patch_then_replan_then_dispatch() -> None:
    state = RuntimeState(workspace_id="w1", pending_requirement_events=["r1"])
    assert next_step_for_state(state) == "requirement_patch"

    state = RuntimeState(workspace_id="w1", replan_reason="no_runnable_work")
    assert next_step_for_state(state) == "planning_and_shaping"

    state = RuntimeState(workspace_id="w1", current_workset=["wp-1"])
    assert next_step_for_state(state) == "batch_dispatch"


def test_run_cycle_selects_and_dispatches_fixture_work() -> None:
    result = run_fixture_cycle("game_project")
    assert result["selected_work_packages"] == ["wp-combat-core"]
    assert result["dispatches"][0]["executor"] == "codex"
    assert result["results"][0]["status"] == "completed"
    assert result["snapshot"]["work_packages"][0]["status"] == "verified"
    assert result["snapshot"]["work_packages"][0]["handoff_notes"] == ["stub execution completed"]
    assert "domain.gaming" in result["runtime"]["selected_knowledge"]
    assert "phase.implementation" in result["runtime"]["selected_knowledge"]
    assert result["runtime"]["specialized_knowledge"]["focus"] == [
        "game",
        "implementation",
        "gameplay",
        "software_engineer",
    ]
    assert result["runtime"]["planning_decision"]["source"] == "mock:mock-structured-v1"
    assert result["runtime"]["planning_decision"]["selected_workset"] == ["wp-combat-core"]
    assert result["runtime"]["node_knowledge_packet"]["focus"]["phase"] == "implementation"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["node_knowledge_packet"]["focus"]["phase"] == "implementation"
    assert "context_pull_manifest" in result["dispatches"][0]["metadata"]["runtime_context"]
    assert "preview" in result["dispatches"][0]["metadata"]["runtime_context"]["context_pull_manifest"]
    assert "pull_strategy" in result["dispatches"][0]["metadata"]["runtime_context"]
    assert "pulled_context" in result["dispatches"][0]["metadata"]["runtime_context"]
    assert result["dispatches"][0]["metadata"]["executor_payload"]["pull_manifest"]["refs"]
    assert result["dispatches"][0]["metadata"]["executor_payload"]["style"] == "execution_heavy"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pull_strategy"]["mode"] == "structured"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pulled_context"]
    assert result["dispatches"][0]["metadata"]["executor_request"]["mode"] == "task_payload"
    assert result["dispatches"][0]["metadata"]["executor_request"]["cycle_id"] == "cycle-0001"
    assert result["dispatches"][0]["metadata"]["executor_request"]["task_type"] == "implementation_or_qa"
    assert result["dispatches"][0]["metadata"]["cycle_id"] == "cycle-0001"
    assert result["dispatches"][0]["metadata"]["execution_ref"] == {
        "cycle_id": "cycle-0001",
        "work_package_id": "wp-combat-core",
        "executor": "codex",
        "execution_id": "codex:wp-combat-core",
    }
    assert result["results"][0]["cycle_id"] == "cycle-0001"
    assert result["results"][0]["execution_ref"] == {
        "cycle_id": "cycle-0001",
        "work_package_id": "wp-combat-core",
        "executor": "codex",
        "execution_id": "codex:wp-combat-core",
    }
    assert result["events"][0]["payload"]["execution_ref"] == {
        "cycle_id": "cycle-0001",
        "work_package_id": "wp-combat-core",
        "executor": "codex",
        "execution_id": "codex:wp-combat-core",
    }
    assert result["events"][-1]["event_type"] == "cycle_completed"


def test_run_cycle_uses_final_result_from_submission_receipt_metadata() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": ["."], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "core",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 1,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
    }

    from devforge.executors.registry import get_executor_adapter

    adapter = get_executor_adapter("codex")
    original_submit_request = adapter.submit_request

    def patched_submit_request(request, *, accepted):
        dispatch = original_submit_request(request, accepted=accepted)
        dispatch.metadata["submission_receipt"]["metadata"]["final_result"] = {
            "execution_id": dispatch.execution_id,
            "work_package_id": "wp-1",
            "cycle_id": "cycle-0001",
            "status": "failed",
            "summary": "real subprocess failure",
            "findings": [],
        }
        return dispatch

    with patch.object(adapter, "submit_request", side_effect=patched_submit_request):
        result = run_cycle(snapshot)

    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["summary"] == "real subprocess failure"
    assert result["snapshot"]["work_packages"][0]["status"] == "failed"


def test_run_fixture_cycle_applies_project_config_override() -> None:
    result = run_fixture_cycle("ecommerce_project")

    assert result["runtime"]["concept_decision"]["source"] == "openrouter:mock-structured-v1"
    assert result["runtime"]["planning_decision"]["source"] == "openrouter:openai/gpt-5.4-mini"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["project_pull_policy_overrides"][0]["budget"] == 444
    assert result["runtime"]["project_llm_preferences"]["provider"] == "openrouter"
    assert result["runtime"]["project_llm_preferences"]["retry_provider"] == "google"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["project_llm_preferences"]["planning_model"] == "openai/gpt-5.4-mini"
    assert "phase.testing" in result["runtime"]["project_knowledge_preferences"]["preferred_ids"]
    assert "phase.testing" in result["runtime"]["selected_knowledge"]
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pull_strategy"]["mode"] == "summary"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pull_strategy"]["budget"] == 444


def test_run_cycle_passes_project_pull_policy_overrides_into_runtime_context() -> None:
    fixture_store = JsonStore("src/devforge/fixtures")
    snapshot = fixture_store.load_snapshot("ecommerce_project")
    snapshot["projects"][0]["pull_policy_overrides"] = [
        {
            "executor": "codex",
            "role_id": "software_engineer",
            "phase": "implementation",
            "mode": "summary",
            "budget": 222,
            "ref_patterns": ["concept_brief.md"],
        }
    ]

    result = run_cycle(snapshot)

    assert result["dispatches"][0]["metadata"]["runtime_context"]["project_pull_policy_overrides"][0]["budget"] == 222
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pull_strategy"]["mode"] == "summary"
    assert result["dispatches"][0]["metadata"]["runtime_context"]["pull_strategy"]["budget"] == 222


def test_run_cycle_works_with_store_loaded_snapshot() -> None:
    fixture_store = JsonStore("src/devforge/fixtures")
    snapshot = fixture_store.load_snapshot("ecommerce_project")
    result = run_cycle(snapshot)
    assert result["selected_work_packages"] == ["wp-cart-frontend"]
    assert result["snapshot"]["work_packages"][0]["status"] == "verified"
    assert result["dispatches"][0]["executor"] == "codex"


def test_run_cycle_seeds_follow_up_work_after_repo_onboarding_is_verified() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "devforge",
            "goal": "onboard repo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "devforge",
                "kind": "existing_repo",
                "status": "active",
                "current_phase": "analysis_design",
                "phases": ["analysis_design", "implementation"],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": ["technical_architect", "execution_planner"],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": ["wp-repo-onboarding"],
                "seam_ids": [],
                "artifacts": {"repo_paths": ["."], "docs": ["README.md"]},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-repo-onboarding",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "analysis_design",
                "domain": "core",
                "role_id": "technical_architect",
                "title": "Existing repository onboarding",
                "goal": "Analyze the repository.",
                "status": "verified",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": ["claude_code"],
                "inputs": [],
                "deliverables": ["docs/devforge/repository-map.md"],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": ["done"],
                "attempt_count": 1,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
    }

    result = run_cycle(snapshot)

    assert result["selected_work_packages"] == ["wp-initial-work-plan"]
    follow_up = next(item for item in result["snapshot"]["work_packages"] if item["work_package_id"] == "wp-initial-work-plan")
    assert follow_up["status"] == "ready"
    assert follow_up["executor"] == "claude_code"
    assert follow_up["retry_action"] == "switch_executor"
    assert follow_up["depends_on"] == ["wp-repo-onboarding"]
    assert "wp-initial-work-plan" in result["snapshot"]["projects"][0]["work_package_ids"]


def test_run_cycle_seeds_implementation_work_after_initial_plan_is_verified() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "devforge",
            "goal": "continue development",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "devforge",
                "kind": "existing_repo",
                "status": "active",
                "current_phase": "analysis_design",
                "phases": ["analysis_design", "implementation"],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": ["execution_planner", "software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": ["wp-repo-onboarding", "wp-initial-work-plan"],
                "seam_ids": [],
                "artifacts": {"repo_paths": ["."], "docs": ["README.md"]},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-repo-onboarding",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "analysis_design",
                "domain": "core",
                "role_id": "technical_architect",
                "title": "Existing repository onboarding",
                "goal": "Analyze the repository.",
                "status": "verified",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": ["claude_code"],
                "inputs": [],
                "deliverables": ["docs/devforge/repository-map.md"],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": ["done"],
                "attempt_count": 1,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            },
            {
                "work_package_id": "wp-initial-work-plan",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "analysis_design",
                "domain": "core",
                "role_id": "execution_planner",
                "title": "Initial implementation backlog",
                "goal": "Plan the next iteration.",
                "status": "verified",
                "priority": 90,
                "executor": "claude_code",
                "fallback_executors": ["claude_code"],
                "inputs": ["wp-repo-onboarding"],
                "deliverables": ["docs/devforge/initial-work-plan.md", "docs/devforge/next-work-packages.json"],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": ["wp-repo-onboarding"],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": ["done"],
                "attempt_count": 1,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            },
        ],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
    }

    result = run_cycle(snapshot)

    seeded_ids = [item["work_package_id"] for item in result["snapshot"]["work_packages"]]
    assert result["snapshot"]["projects"][0]["current_phase"] == "implementation"
    assert "wp-runtime-state-persistence" in seeded_ids
    assert "wp-executor-live-adapters" in seeded_ids
    assert "wp-onboarding-entry-flow" in seeded_ids
    assert result["selected_work_packages"] == ["wp-runtime-state-persistence"]


def test_run_cycle_persists_events_artifacts_and_memory_when_stores_are_injected(tmp_path) -> None:
    fixture_store = JsonStore("src/devforge/fixtures")
    snapshot = fixture_store.load_snapshot("game_project")
    event_store = JsonlEventStore(tmp_path / "events.jsonl")
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    memory_store = JsonMemoryStore(tmp_path / "memory")

    result = run_cycle(
        snapshot,
        event_store=event_store,
        artifact_store=artifact_store,
        memory_store=memory_store,
    )

    events = event_store.list_events()
    assert len(events) == len(result["events"])
    assert any(event["event_type"] == "work_package_dispatched" for event in events)
    assert artifact_store.read_text("runtime/game-client/concept_decision.json")
    assert artifact_store.read_text("runtime/game-client/cycle-0001/concept_decision.json")
    concept_brief = artifact_store.read_text("runtime/game-client/concept_brief.md")
    assert "Concept Brief" in concept_brief
    assert "Focus Areas" in concept_brief
    acceptance_goals = artifact_store.read_text("runtime/game-client/acceptance_goals.json")
    assert "collect concept model for Game Client" in acceptance_goals
    assert artifact_store.read_text("runtime/game-client/node_knowledge_packet.json")
    assert artifact_store.read_text("runtime/game-client/cycle-0001/node_knowledge_packet.json")
    latest_concept_memory = memory_store.load_memory("project/game-client", "latest-concept-decision")
    assert latest_concept_memory["metadata"]["kind"] == "concept_decision"
    assert latest_concept_memory["metadata"]["cycle_id"] == "cycle-0001"
    cycle_concept_memory = memory_store.load_memory("project/game-client", "cycle-0001-concept-decision")
    assert cycle_concept_memory["metadata"]["cycle_id"] == "cycle-0001"
    latest_concept_brief = memory_store.load_memory("project/game-client", "latest-concept-brief")
    assert latest_concept_brief["metadata"]["kind"] == "concept_brief"
    latest_acceptance_goals = memory_store.load_memory("project/game-client", "latest-acceptance-goals")
    assert latest_acceptance_goals["metadata"]["kind"] == "acceptance_goals"
    latest_memory = memory_store.load_memory("project/game-client", "latest-specialized-knowledge")
    assert latest_memory["metadata"]["kind"] == "specialized_knowledge"
    assert latest_memory["metadata"]["cycle_id"] == "cycle-0001"
    cycle_memory = memory_store.load_memory("project/game-client", "cycle-0001-specialized-knowledge")
    assert cycle_memory["metadata"]["cycle_id"] == "cycle-0001"


def test_run_cycle_accepts_grouped_workspace_persistence(tmp_path) -> None:
    fixture_store = JsonStore("src/devforge/fixtures")
    snapshot = fixture_store.load_snapshot("game_project")
    persistence = WorkspacePersistence(
        event_store=JsonlEventStore(tmp_path / "events.jsonl"),
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
        memory_store=JsonMemoryStore(tmp_path / "memory"),
    )

    result = run_cycle(snapshot, persistence=persistence)

    assert any(event["event_type"] == "cycle_completed" for event in result["events"])
    assert persistence.event_store is not None
    assert len(persistence.event_store.list_events()) == len(result["events"])


def test_run_cycle_works_with_local_workspace_persistence_factory(tmp_path) -> None:
    fixture_store = JsonStore("src/devforge/fixtures")
    snapshot = fixture_store.load_snapshot("game_project")
    persistence = build_local_workspace_persistence(tmp_path / "runtime")

    result = run_cycle(snapshot, persistence=persistence)
    second_result = run_cycle(snapshot, persistence=persistence)

    assert persistence.event_store is not None
    assert persistence.snapshot_store is not None
    assert len(persistence.event_store.list_events()) == len(result["events"]) + len(second_result["events"])
    assert result["runtime"]["cycle_id"] == "cycle-0001"
    assert second_result["runtime"]["cycle_id"] == "cycle-0002"
    assert persistence.snapshot_store.load_snapshot("latest")["initiative"]["initiative_id"] == "game-001"
    assert persistence.snapshot_store.load_snapshot("workspace-game-001-latest")["initiative"]["initiative_id"] == "game-001"
    assert persistence.snapshot_store.load_snapshot("initiative-game-001-latest")["initiative"]["initiative_id"] == "game-001"
    assert persistence.snapshot_store.load_snapshot("project-game-client-latest")["projects"][0]["project_id"] == "game-client"
    assert persistence.snapshot_store.load_snapshot("workspace-game-001-cycle-0001")["initiative"]["initiative_id"] == "game-001"
    assert persistence.snapshot_store.load_snapshot("workspace-game-001-cycle-0002")["initiative"]["initiative_id"] == "game-001"


def test_run_cycle_marks_failed_when_executor_rejects_work() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "python",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 1,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [],
    }
    result = run_cycle(snapshot)
    assert result["dispatches"][0]["accepted"] is False
    assert result["results"][0]["status"] == "failed"
    assert result["snapshot"]["work_packages"][0]["status"] == "failed"
    assert result["snapshot"]["work_packages"][0]["attempt_count"] == 1
    assert result["snapshot"]["work_packages"][0]["last_execution_ref"]["execution_id"] == "python:wp-1"


def test_run_cycle_requeues_failed_work_when_attempts_remain() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "python",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [],
    }

    result = run_cycle(snapshot)

    assert result["results"][0]["status"] == "failed"
    assert result["snapshot"]["work_packages"][0]["status"] == "ready"
    assert result["snapshot"]["work_packages"][0]["attempt_count"] == 1
    assert result["snapshot"]["work_packages"][0]["execution_history"][0]["cycle_id"] == "cycle-0001"
    assert any(event["event_type"] == "work_package_requeued" for event in result["events"])


def test_run_cycle_switches_executor_on_rejected_work_when_fallback_exists() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "python",
                "fallback_executors": ["codex"],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [],
    }

    result = run_cycle(snapshot)

    assert result["snapshot"]["work_packages"][0]["status"] == "ready"
    assert result["snapshot"]["work_packages"][0]["executor"] == "codex"
    assert result["snapshot"]["work_packages"][0]["retry_action"] == "switch_executor"
    assert result["snapshot"]["work_packages"][0]["retry_source"] == "mock:mock-structured-v1"
    assert result["snapshot"]["work_packages"][0]["retry_confidence"] == 0.72
    assert any(event["event_type"] == "work_package_executor_switched" for event in result["events"])


def test_apply_executor_result_blocks_work_on_contract_failure() -> None:
    snapshot = {
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "python",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": ["seam-1"],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [
            {
                "seam_id": "seam-1",
                "initiative_id": "i1",
                "source_project_id": "p1",
                "target_project_id": "p2",
                "type": "api",
                "name": "front/back seam",
                "status": "draft",
                "contract_version": "v1",
                "owner_role_id": "integration_owner",
                "owner_executor": "claude_code",
                "artifacts": [],
                "acceptance_criteria": [],
                "risks": [],
                "related_work_packages": ["wp-1"],
                "change_log": [],
                "verification_refs": [],
                "created_at": None,
                "updated_at": None,
            }
        ],
    }
    result = {
        "execution_id": "codex:wp-1",
        "work_package_id": "wp-1",
        "cycle_id": "cycle-0001",
        "status": "failed",
        "summary": "contract mismatch detected",
        "execution_ref": {
            "cycle_id": "cycle-0001",
            "work_package_id": "wp-1",
            "executor": "codex",
            "execution_id": "codex:wp-1",
        },
    }

    _apply_executor_result(
        snapshot,
        result,
        retry_context={
            "requirement_patch_applied": False,
            "related_seams": snapshot["seams"],
            "specialized_knowledge": {"focus": ["ecommerce", "integration"]},
            "node_knowledge_packet": {"focus": {"phase": "testing", "role_id": "qa_engineer", "domain": "integration"}},
            "requirement_events": [],
        },
    )

    assert snapshot["work_packages"][0]["status"] == "blocked"
    assert snapshot["work_packages"][0]["retry_action"] == "block"
    assert snapshot["work_packages"][0]["retry_source"] == "mock:mock-structured-v1"


def test_apply_executor_result_requests_replan_when_requirement_patch_happened() -> None:
    snapshot = {
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "python",
                "fallback_executors": ["codex"],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ]
    }
    result = {
        "execution_id": "python:wp-1",
        "work_package_id": "wp-1",
        "cycle_id": "cycle-0001",
        "status": "failed",
        "summary": "python request rejected",
        "execution_ref": {
            "cycle_id": "cycle-0001",
            "work_package_id": "wp-1",
            "executor": "python",
            "execution_id": "python:wp-1",
        },
    }

    _apply_executor_result(snapshot, result, retry_context={"requirement_patch_applied": True})

    assert snapshot["work_packages"][0]["status"] == "blocked"
    assert snapshot["work_packages"][0]["retry_action"] == "replan"
    assert snapshot["work_packages"][0]["retry_source"] == "mock:mock-structured-v1"
    assert snapshot["work_packages"][0]["replan_required"] is True


def test_run_cycle_applies_requirement_patch_before_selection() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": ["req-1"],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation", "requirement_patch"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer", "execution_planner"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": ["req-1"],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [],
        "requirement_events": [
            {
                "requirement_event_id": "req-1",
                "initiative_id": "i1",
                "project_ids": ["p1"],
                "type": "modify",
                "summary": "change frontend plan",
                "details": "",
                "source": "user",
                "impact_level": "medium",
                "affected_domains": ["frontend"],
                "affected_work_packages": ["wp-1"],
                "affected_seams": [],
                "patch_status": "recorded",
                "created_at": None,
                "applied_at": None,
            }
        ],
    }
    result = run_cycle(snapshot)
    work_package_ids = [item["work_package_id"] for item in result["snapshot"]["work_packages"]]
    assert "requirement-patch-req-1" in work_package_ids
    assert result["snapshot"]["work_packages"][0]["status"] == "deprecated"
    assert result["snapshot"]["requirement_events"][0]["patch_status"] == "applied"


def test_run_cycle_blocks_work_when_split_generated_seam_is_not_frozen() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["front"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "front",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "front",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": ["seam-front-back"],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "front",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": ["seam-front-back"],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [
            {
                "seam_id": "seam-front-back",
                "initiative_id": "i1",
                "source_project_id": "front",
                "target_project_id": "back",
                "type": "api",
                "name": "front/back seam",
                "status": "draft",
                "contract_version": "v1",
                "owner_role_id": "integration_owner",
                "owner_executor": "claude_code",
                "artifacts": [],
                "acceptance_criteria": [],
                "risks": [],
                "related_work_packages": ["wp-1"],
                "change_log": [],
                "verification_refs": [],
                "created_at": None,
                "updated_at": None,
            }
        ],
    }
    result = run_cycle(snapshot)
    assert result["selected_work_packages"] == []
    assert result["dispatches"] == []
    assert result["results"] == []
    assert result["runtime"]["selected_knowledge"] == ["phase.implementation"]


def test_run_cycle_falls_back_to_project_phase_for_knowledge_selection() -> None:
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "concept_collect",
                "phases": ["concept_collect"],
                "project_archetype": "ecommerce",
                "domains": ["frontend"],
                "active_roles": ["product_manager"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": [],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [],
        "seams": [],
    }
    result = run_cycle(snapshot)
    assert result["runtime"]["selected_knowledge"] == [
        "domain.ecommerce",
        "phase.concept_collect",
    ]
    assert result["runtime"]["concept_decision"]["source"] == "mock:mock-structured-v1"
    assert result["runtime"]["concept_decision"]["focus_areas"] == [
        "ecommerce",
        "concept_collect",
    ]
    assert result["runtime"]["specialized_knowledge"]["focus"] == [
        "ecommerce",
        "concept_collect",
    ]
    assert result["runtime"]["node_knowledge_packet"] == {}


def test_langgraph_builder_runs_minimal_flow() -> None:
    graph = build_meta_graph()
    result = graph.invoke(
        RuntimeState(
            workspace_id="w1",
            foreground_project="p1",
            current_workset=["wp-1"],
        ).to_dict()
    )
    assert result["active_project_id"] == "p1"
    assert result["running_queue"] == []
    assert result["recent_executor_results"] == ["verified:wp-1"]


def test_langgraph_builder_applies_requirement_patch_route() -> None:
    graph = build_meta_graph()
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "demo",
            "goal": "demo",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": ["req-1"],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "demo",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation", "requirement_patch"],
                "project_archetype": "demo",
                "domains": ["frontend"],
                "active_roles": ["software_engineer", "execution_planner"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-1"],
                "seam_ids": [],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": ["req-1"],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-1",
                "initiative_id": "i1",
                "project_id": "p1",
                "phase": "implementation",
                "domain": "frontend",
                "role_id": "software_engineer",
                "title": "demo",
                "goal": "demo",
                "status": "ready",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": [],
                "inputs": [],
                "deliverables": [],
                "constraints": [],
                "acceptance_criteria": [],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "seams": [],
        "requirement_events": [
            {
                "requirement_event_id": "req-1",
                "initiative_id": "i1",
                "project_ids": ["p1"],
                "type": "modify",
                "summary": "change frontend plan",
                "details": "",
                "source": "user",
                "impact_level": "medium",
                "affected_domains": ["frontend"],
                "affected_work_packages": ["wp-1"],
                "affected_seams": [],
                "patch_status": "recorded",
                "created_at": None,
                "applied_at": None,
            }
        ],
    }
    result = graph.invoke(
        RuntimeState(
            workspace_id="w1",
            foreground_project="p1",
            current_workset=["wp-1"],
            pending_requirement_events=["req-1"],
            snapshot=snapshot,
        ).to_dict()
    )
    assert result["active_project_id"] == "p1"
    assert result["pending_requirement_events"] == []
    assert result["recent_executor_results"] == ["verified:wp-1"]
    assert result["snapshot"]["requirement_events"][0]["patch_status"] == "applied"
    assert result["snapshot"]["work_packages"][0]["status"] == "deprecated"
