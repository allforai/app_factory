from pathlib import Path

from devforge.persistence import (
    FileArtifactStore,
    JsonMemoryStore,
    JsonStore,
    JsonlEventStore,
    SQLiteEventStore,
    SQLiteSnapshotStore,
    build_local_workspace_persistence,
    sqlite_schema,
)
from devforge.planning import apply_project_split, apply_requirement_events, freeze_seam, verify_seam
from devforge.state import RequirementEvent


def test_json_store_lists_loads_and_saves_snapshots(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    store.save_snapshot("demo", {"hello": "world"})

    assert store.list_snapshots() == ["demo.json"]
    assert store.load_snapshot("demo") == {"hello": "world"}


def test_json_store_can_apply_patch(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    store.save_snapshot("demo", {"projects": [{"id": "p1"}], "queue": ["a"]})

    updated = store.apply_patch(
        "demo",
        [
            {"action": "add", "target": "projects", "value": {"id": "p2"}},
            {"action": "append_unique", "target": "queue", "value": "b"},
        ],
        save_as="demo-next",
    )

    assert updated["projects"] == [{"id": "p1"}, {"id": "p2"}]
    assert updated["queue"] == ["a", "b"]
    assert store.load_snapshot("demo-next") == updated


def test_jsonl_event_store_appends_and_filters_events(tmp_path: Path) -> None:
    store = JsonlEventStore(tmp_path / "events.jsonl")
    store.append_event({"event_id": "e1", "event_type": "work_package_dispatched", "scope_id": "wp-1"})
    store.append_event({"event_id": "e2", "event_type": "seam_frozen", "scope_id": "seam-1"})

    assert len(store.list_events()) == 2
    assert store.list_events(event_type="seam_frozen") == [
        {"event_id": "e2", "event_type": "seam_frozen", "scope_id": "seam-1"}
    ]
    assert store.list_events(scope_id="wp-1") == [
        {"event_id": "e1", "event_type": "work_package_dispatched", "scope_id": "wp-1"}
    ]


def test_file_artifact_store_writes_reads_and_lists_artifacts(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path / "artifacts")
    saved_path = store.write_text("reports/acceptance.md", "# acceptance")

    assert saved_path == "reports/acceptance.md"
    assert store.read_text("reports/acceptance.md") == "# acceptance"
    assert store.list_artifacts("reports") == ["reports/acceptance.md"]


def test_json_memory_store_persists_namespaced_memories(tmp_path: Path) -> None:
    store = JsonMemoryStore(tmp_path / "memory")
    store.save_memory(
        "project/game-client",
        "combat-rules",
        "single-player prototype first",
        metadata={"source": "planning"},
    )

    loaded = store.load_memory("project/game-client", "combat-rules")
    assert loaded["content"] == "single-player prototype first"
    assert loaded["metadata"] == {"source": "planning"}
    assert len(store.list_memories("project/game-client")) == 1


def test_sqlite_snapshot_store_persists_and_lists_snapshots(tmp_path: Path) -> None:
    store = SQLiteSnapshotStore(tmp_path / "workspace.sqlite3")
    store.save_snapshot("demo", {"hello": "sqlite"})

    assert store.list_snapshots() == ["demo"]
    assert store.load_snapshot("demo") == {"hello": "sqlite"}


def test_sqlite_event_store_appends_and_filters_events(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "workspace.sqlite3")
    store.append_event({"event_id": "e1", "event_type": "cycle_completed", "scope_id": "i1", "payload": {"ok": True}})
    store.append_event({"event_id": "e2", "event_type": "work_package_dispatched", "scope_id": "wp-1", "payload": {}})

    assert len(store.list_events()) == 2
    assert store.list_events(event_type="cycle_completed")[0]["payload"] == {"ok": True}
    assert store.list_events(scope_id="wp-1")[0]["event_id"] == "e2"


def test_build_local_workspace_persistence_creates_default_layout(tmp_path: Path) -> None:
    persistence = build_local_workspace_persistence(tmp_path / "runtime")

    assert persistence.snapshot_store is not None
    assert persistence.event_store is not None
    assert persistence.artifact_store is not None
    assert persistence.memory_store is not None


def test_sqlite_schema_covers_state_event_artifact_and_memory_layers() -> None:
    schema = sqlite_schema()

    assert "CREATE TABLE IF NOT EXISTS snapshots" in schema
    assert "CREATE TABLE IF NOT EXISTS events" in schema
    assert "CREATE TABLE IF NOT EXISTS artifacts" in schema
    assert "CREATE TABLE IF NOT EXISTS memories" in schema


def test_apply_requirement_events_deprecates_and_adds_patch_work() -> None:
    snapshot = {
        "work_packages": [
            {"work_package_id": "wp-1", "status": "ready"},
        ],
        "requirement_events": [
            {
                "requirement_event_id": "req-1",
                "initiative_id": "i1",
                "project_ids": ["p1"],
                "type": "modify",
                "summary": "change cart logic",
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
    events = [
        RequirementEvent(
            requirement_event_id="req-1",
            initiative_id="i1",
            project_ids=["p1"],
            type="modify",
            summary="change cart logic",
            affected_domains=["frontend"],
            affected_work_packages=["wp-1"],
        )
    ]

    updated = apply_requirement_events(snapshot, events)
    assert updated["work_packages"][0]["status"] == "deprecated"
    assert updated["work_packages"][1]["work_package_id"] == "requirement-patch-req-1"
    assert updated["requirement_events"][0]["patch_status"] == "applied"


def test_apply_project_split_creates_children_and_seam() -> None:
    snapshot = {
        "projects": [
            {
                "project_id": "app-root",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "App Root",
                "kind": "fullstack",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "ecommerce",
                "domains": ["frontend", "backend"],
                "active_roles": ["software_engineer", "integration_owner"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-front", "wp-back"],
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
            {"work_package_id": "wp-front", "project_id": "app-root"},
            {"work_package_id": "wp-back", "project_id": "app-root"},
        ],
        "seams": [],
    }

    updated = apply_project_split(
        snapshot,
        source_project_id="app-root",
        child_projects=[
            {
                "project_id": "app-front",
                "initiative_id": "i1",
                "parent_project_id": "app-root",
                "name": "App Front",
                "kind": "frontend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "ecommerce",
                "domains": ["frontend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-front"],
                "seam_ids": ["seam-front-back"],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            },
            {
                "project_id": "app-back",
                "initiative_id": "i1",
                "parent_project_id": "app-root",
                "name": "App Back",
                "kind": "backend",
                "status": "active",
                "current_phase": "implementation",
                "phases": ["implementation"],
                "project_archetype": "ecommerce",
                "domains": ["backend"],
                "active_roles": ["software_engineer"],
                "concept_model_refs": [],
                "contracts": [],
                "executor_policy_ref": None,
                "work_package_ids": ["wp-back"],
                "seam_ids": ["seam-front-back"],
                "artifacts": {"repo_paths": [], "docs": []},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            },
        ],
        seam={
            "seam_id": "seam-front-back",
            "initiative_id": "i1",
            "source_project_id": "app-front",
            "target_project_id": "app-back",
            "type": "api",
            "name": "frontend/backend seam",
            "status": "draft",
            "contract_version": "v1",
            "owner_role_id": "integration_owner",
            "owner_executor": "claude_code",
            "artifacts": [],
            "acceptance_criteria": [],
            "risks": [],
            "related_work_packages": ["wp-front", "wp-back"],
            "change_log": [],
            "verification_refs": [],
            "created_at": None,
            "updated_at": None,
        },
        work_package_assignment={
            "wp-front": "app-front",
            "wp-back": "app-back",
        },
    )

    assert updated["projects"][0]["status"] == "split_done"
    assert updated["projects"][0]["coordination_project"] is True
    assert updated["projects"][0]["children"] == ["app-front", "app-back"]
    assert updated["seams"][0]["seam_id"] == "seam-front-back"
    assert updated["projects"][1]["seam_ids"] == ["seam-front-back"]
    assert updated["projects"][2]["seam_ids"] == ["seam-front-back"]
    assert updated["work_packages"][0]["project_id"] == "app-front"
    assert updated["work_packages"][1]["project_id"] == "app-back"
    assert updated["work_packages"][0]["related_seams"] == ["seam-front-back"]
    assert updated["work_packages"][1]["related_seams"] == ["seam-front-back"]


def test_freeze_and_verify_seam_progress_lifecycle() -> None:
    snapshot = {
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
                "related_work_packages": [],
                "change_log": [],
                "verification_refs": [],
                "created_at": None,
                "updated_at": None,
            }
        ]
    }

    frozen = freeze_seam(snapshot, "seam-front-back", summary="contract frozen")
    assert frozen["seams"][0]["status"] == "frozen"
    assert frozen["seams"][0]["change_log"][-1]["summary"] == "contract frozen"

    verified = verify_seam(frozen, "seam-front-back", summary="integration verified")
    assert verified["seams"][0]["status"] == "verified"
    assert verified["seams"][0]["change_log"][-1]["summary"] == "integration verified"
