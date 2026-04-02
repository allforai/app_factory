import json

from devforge.main import main, run_snapshot_cycle


def test_main_fixture_command_prints_summary(capsys) -> None:
    exit_code = main(["fixture", "game_project"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["cycle_id"] == "cycle-0001"
    assert payload["selected_work_packages"] == ["wp-combat-core"]


def test_main_snapshot_command_supports_project_config_and_json(capsys, tmp_path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    project_config_path = tmp_path / "snapshot.project_config.json"
    snapshot_path.write_text(
        json.dumps(
            {
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
                        "project_archetype": "ecommerce",
                        "domains": ["frontend"],
                        "active_roles": ["software_engineer"],
                        "concept_model_refs": [],
                        "contracts": [],
                        "pull_policy_overrides": [],
                        "llm_preferences": {},
                        "knowledge_preferences": {},
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
                "seams": [],
            }
        ),
        encoding="utf-8",
    )
    project_config_path.write_text(
        json.dumps(
            {
                "projects": {
                    "p1": {
                        "knowledge_preferences": {"preferred_ids": ["phase.testing"], "excluded_ids": []}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["snapshot", str(snapshot_path), "--project-config", str(project_config_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert "phase.testing" in payload["runtime"]["selected_knowledge"]


def test_run_snapshot_cycle_supports_persistence_root(tmp_path) -> None:
    fixture_snapshot = {
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
                "project_archetype": "ecommerce",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
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
        "seams": [],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(fixture_snapshot), encoding="utf-8")

    result = run_snapshot_cycle(snapshot_path, persistence_root=tmp_path / "runtime")

    assert result["runtime"]["cycle_id"] == "cycle-0001"
    assert (tmp_path / "runtime" / "workspace.sqlite3").exists()
