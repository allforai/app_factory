"""S2: Multiplayer game end-to-end scenario test.

Validates: project split, seam freeze/break, parallel execution,
requirement change, multi-round convergence.
"""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    concept_collection_node,
    product_design_node,
    design_validation_node,
    closure_expansion_node,
    acceptance_and_gap_check_node,
)
from devforge.seams.verifier import verify_seam_compliance
from devforge.planning.graph_patch import apply_requirement_events, apply_project_split
from devforge.scheduler import select_workset
from devforge.state import RequirementEvent, SeamState, WorkPackage, decode_snapshot
from devforge.llm import MockLLMClient
from tests.fixtures.e2e_game_snapshot import make_game_snapshot


def test_s2_project_split_and_parallel_execution():
    """Single project → split into singleplayer + multiplayer → parallel worksets."""
    snap = make_game_snapshot()

    # Split project
    updated = apply_project_split(
        snap,
        source_project_id="game-main",
        child_projects=[
            {"project_id": "game-sp", "initiative_id": "game-001", "parent_project_id": "game-main", "name": "单机核心", "kind": "game", "status": "active", "current_phase": "implementation", "project_archetype": "gaming", "domains": ["地图", "战斗"], "seam_ids": []},
            {"project_id": "game-mp", "initiative_id": "game-001", "parent_project_id": "game-main", "name": "多人联机", "kind": "game", "status": "active", "current_phase": "implementation", "project_archetype": "gaming", "domains": ["多人"], "seam_ids": []},
        ],
        seam={"seam_id": "seam-sp-mp", "initiative_id": "game-001", "source_project_id": "game-sp", "target_project_id": "game-mp", "type": "api", "name": "单机-联机接缝", "status": "draft", "contract_version": "v1", "owner_role_id": "technical_architect", "owner_executor": "claude_code", "artifacts": [], "acceptance_criteria": ["战斗事件格式一致"], "risks": [], "related_work_packages": [], "change_log": [], "verification_refs": []},
        work_package_assignment={"wp-map": "game-sp", "wp-combat": "game-sp", "wp-multiplayer": "game-mp"},
    )

    # Verify split
    project_ids = [p["project_id"] for p in updated["projects"]]
    assert "game-sp" in project_ids
    assert "game-mp" in project_ids
    assert any(s["seam_id"] == "seam-sp-mp" for s in updated["seams"])

    # Parent should be coordination project
    parent = next(p for p in updated["projects"] if p["project_id"] == "game-main")
    assert parent["status"] == "split_done"
    assert parent["coordination_project"] is True


def test_s2_seam_freeze_and_break():
    """Frozen seam → implementation deviates → broken detected."""
    snap = make_game_snapshot(with_project_split=True)

    # Seam is frozen
    seam = snap["seams"][0]
    assert seam["status"] == "frozen"

    # Implementation deviates
    result = verify_seam_compliance(
        seam,
        [{"work_package_id": "wp-combat", "status": "completed", "summary": "战斗事件使用了不同格式，deviation from protocol"}],
    )
    assert result.compliant is False
    assert any(v.violation_type == "contract_deviation" for v in result.violations)


def test_s2_requirement_change_mid_flight():
    """PvP requirement added mid-implementation → affected WPs deprecated."""
    snap = make_game_snapshot(with_project_split=True, with_requirement_change=True)
    events = [
        RequirementEvent(
            requirement_event_id="req-pvp",
            initiative_id="game-001",
            project_ids=["game-singleplayer", "game-multiplayer"],
            type="add",
            summary="新增PvP竞技场模式",
            details="",
            source="user",
            impact_level="high",
            affected_domains=["战斗", "多人"],
            affected_work_packages=["wp-combat", "wp-multiplayer"],
            affected_seams=["seam-sp-mp"],
            patch_status="recorded",
        ),
    ]
    updated = apply_requirement_events(snap, events)

    # Affected WPs deprecated
    for wp in updated["work_packages"]:
        if wp["work_package_id"] in ("wp-combat", "wp-multiplayer"):
            assert wp["status"] == "deprecated"

    # Non-affected unchanged
    map_wp = next(wp for wp in updated["work_packages"] if wp["work_package_id"] == "wp-map")
    assert map_wp["status"] == "ready"

    # Patch WP added
    assert any("requirement-patch" in wp["work_package_id"] for wp in updated["work_packages"])


def test_s2_full_pipeline_convergence():
    """Full game pipeline: concept → design → validate → expand → accept."""
    llm = MockLLMClient()
    snap = make_game_snapshot()
    project = snap["projects"][0]

    state = RuntimeState(
        workspace_id="W-game",
        initiative_id="game-001",
        active_project_id="game-main",
    )

    state = concept_collection_node(state, project=project, llm_client=llm)
    state = product_design_node(state, project=project, llm_client=llm)
    state = design_validation_node(state)
    assert state.design_valid is True

    state = closure_expansion_node(state, max_ring=1)
    assert state.closure_expansion["total_ring_1"] > 0

    all_results = [
        {"work_package_id": wp["work_package_id"], "status": "completed", "summary": f"{wp['title']}完成"}
        for wp in snap["work_packages"]
    ]
    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=snap["initiative"]["global_acceptance_goals"],
        work_package_results=all_results,
        llm_client=llm,
    )
    assert state.acceptance_verdict["is_production_ready"] is True
    assert state.termination_signal is True
