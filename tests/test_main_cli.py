import json
from pathlib import Path

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


def test_main_init_command_writes_all_files_into_runtime_directory(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(["init"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    runtime_root = tmp_path / ".devforge-runtime"
    snapshot_path = runtime_root / "devforge.snapshot.json"
    project_config_path = runtime_root / "devforge.project_config.json"

    assert exit_code == 0
    assert payload["runtime_root"] == ".devforge-runtime"
    assert payload["snapshot_path"] == ".devforge-runtime/devforge.snapshot.json"
    assert payload["project_config_path"] == ".devforge-runtime/devforge.project_config.json"
    assert snapshot_path.exists()
    assert project_config_path.exists()

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["projects"][0]["artifacts"]["repo_paths"] == ["."]
    assert snapshot["work_packages"][0]["work_package_id"] == "wp-repo-onboarding"


def test_main_init_command_refuses_to_overwrite_existing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runtime_root = tmp_path / ".devforge-runtime"
    runtime_root.mkdir()
    (runtime_root / "devforge.snapshot.json").write_text("{}", encoding="utf-8")

    try:
        main(["init"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected parser error when init would overwrite files")


def test_main_init_workspace_command_creates_guardian_entry(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "pyproject.toml").write_text("[project]\nname='api'\n", encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text('{"name":"web"}\n', encoding="utf-8")

    exit_code = main(["init", "--workspace", "--name", "Demo Workspace"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    snapshot_path = tmp_path / ".devforge-runtime" / "devforge.snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["mode"] == "workspace"
    assert set(payload["discovered_projects"]) == {"api", "web"}
    assert snapshot["initiative"]["scheduler_state"]["foreground_project"] == "demo-workspace-guardian"
    assert snapshot["projects"][0]["coordination_project"] is True
    assert snapshot["projects"][0]["children"] == ["api", "web"]
    assert snapshot["work_packages"][0]["work_package_id"] == "wp-workspace-guardian"
