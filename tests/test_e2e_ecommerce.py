"""S1: E-commerce end-to-end scenario test.

Validates: design back-loop, executor failure recovery, product acceptance back-loop,
multi-round convergence.
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
from devforge.planning.graph_patch import apply_requirement_events
from devforge.state import RequirementEvent
from devforge.llm import MockLLMClient
from tests.fixtures.e2e_ecommerce_snapshot import make_ecommerce_snapshot


def test_s1_happy_path_converges():
    """Full pipeline: concept → design → validate → expand → accept → terminate."""
    llm = MockLLMClient()
    snap = make_ecommerce_snapshot()
    project = snap["projects"][0]

    state = RuntimeState(
        workspace_id="W-ecom",
        initiative_id="ecom-001",
        active_project_id="ecom-main",
        foreground_project="ecom-main",
    )

    # Round 1: Concept
    state = concept_collection_node(state, project=project, llm_client=llm)
    assert state.concept_decision is not None

    # Round 2: Design
    state = product_design_node(state, project=project, llm_client=llm)
    assert len(state.product_design["domains"]) >= 4

    # Round 3: Validate
    state = design_validation_node(state)
    assert state.design_valid is True

    # Round 4: Closure expansion
    state = closure_expansion_node(state, max_ring=2)
    assert state.closure_expansion["total_ring_1"] > 0
    assert state.closure_expansion["coverage_ratio"] >= 0.8

    # Round 5: Seam check — verifier uses seam["id"], so provide both keys
    seam = {**snap["seams"][0], "id": snap["seams"][0]["seam_id"]}
    seam_result = verify_seam_compliance(
        seam,
        [{"work_package_id": "wp-order", "status": "completed", "summary": "订单ID传递正确，支付状态回调正确，幂等性保证满足"}],
    )
    assert seam_result.compliant is True

    # Round 6: Acceptance
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


def test_s1_failure_recovery_and_replan():
    """Executor failure → retry → acceptance fail → gap → replan."""
    llm = MockLLMClient()
    snap = make_ecommerce_snapshot(with_failures=True)
    project = snap["projects"][0]

    state = RuntimeState(
        workspace_id="W-ecom",
        initiative_id="ecom-001",
        active_project_id="ecom-main",
    )

    # Design pipeline
    state = concept_collection_node(state, project=project, llm_client=llm)
    state = product_design_node(state, project=project, llm_client=llm)
    state = design_validation_node(state)
    assert state.design_valid is True

    # Acceptance with failures
    results = []
    for wp in snap["work_packages"]:
        results.append({
            "work_package_id": wp["work_package_id"],
            "status": wp["status"] if wp["status"] in ("failed",) else "completed",
            "summary": wp.get("findings", [{}])[0].get("summary", f"{wp['title']}完成") if wp["status"] == "failed" else f"{wp['title']}完成",
        })

    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=snap["initiative"]["global_acceptance_goals"],
        work_package_results=results,
        llm_client=llm,
    )

    # Should NOT be production ready due to payment failure
    assert state.acceptance_verdict["is_production_ready"] is False
    assert state.termination_signal is not True
    assert "acceptance" in state.replan_reason


def test_s1_requirement_change_applied():
    """Mid-flight requirement change → patch applied."""
    snap = make_ecommerce_snapshot(with_requirement_change=True)
    # Use type="modify" so apply_requirement_events deprecates the affected WPs
    events = [
        RequirementEvent(
            requirement_event_id="req-coupon",
            initiative_id="ecom-001",
            project_ids=["ecom-main"],
            type="modify",
            summary="新增优惠券功能",
            details="",
            source="user",
            impact_level="medium",
            affected_domains=["交易", "支付"],
            affected_work_packages=["wp-order", "wp-payment"],
            affected_seams=["seam-order-payment"],
            patch_status="recorded",
        ),
    ]
    updated_snap = apply_requirement_events(snap, events)

    # Patch work package should be added
    wp_ids = [wp["work_package_id"] for wp in updated_snap["work_packages"]]
    assert any("requirement-patch" in wp_id for wp_id in wp_ids)

    # Affected work packages should be deprecated
    for wp in updated_snap["work_packages"]:
        if wp["work_package_id"] in ("wp-order", "wp-payment"):
            assert wp["status"] == "deprecated"

    # Non-affected should be unchanged
    auth_wp = next(wp for wp in updated_snap["work_packages"] if wp["work_package_id"] == "wp-auth")
    assert auth_wp["status"] == "verified"


def test_s1_seam_broken_detected():
    """Seam compliance check catches deviation."""
    snap = make_ecommerce_snapshot()
    # Verifier uses seam["id"]; provide both keys to match the snapshot seam_id
    seam = {**snap["seams"][0], "id": snap["seams"][0]["seam_id"]}
    result = verify_seam_compliance(
        seam,
        [{"work_package_id": "wp-payment", "status": "completed", "summary": "支付实现但返回格式与合约不一致，deviation from JSON contract"}],
    )
    assert result.compliant is False
    assert any(v.violation_type == "contract_deviation" for v in result.violations)
