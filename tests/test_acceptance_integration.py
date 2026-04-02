"""Integration: results → seam check → acceptance → gap → remediation."""
from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import acceptance_and_gap_check_node
from devforge.seams.verifier import verify_seam_compliance
from devforge.llm import MockLLMClient

def test_full_acceptance_pass_pipeline():
    """All work done → seams verified → acceptance passes → terminate."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1", cycle_id="cycle-005")
    state.product_design = {"product_name": "电商平台", "ring_0_tasks": ["购买", "支付"], "user_flows": [{"role": "buyer"}, {"role": "admin"}], "domains": []}
    state.closure_expansion = {"total_ring_0": 2, "total_ring_1": 6, "coverage_ratio": 0.9, "closures": []}

    seam = {"seam_id": "S-1", "status": "frozen", "acceptance_criteria": ["API returns JSON"], "artifacts": []}
    seam_result = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "completed", "summary": "API returns JSON correctly"}])
    assert seam_result.compliant is True

    state = acceptance_and_gap_check_node(state, acceptance_goals=["购买流程完整", "支付安全"], work_package_results=[{"work_package_id": "WP-1", "status": "completed", "summary": "购买流程实现"}, {"work_package_id": "WP-2", "status": "completed", "summary": "支付功能完成"}], llm_client=llm)
    assert state.acceptance_verdict["is_production_ready"] is True
    assert state.termination_signal is True

def test_full_acceptance_fail_pipeline():
    """Work failed → acceptance fails → gap analysis → replan."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1", cycle_id="cycle-005")
    state.product_design = {"product_name": "电商平台", "ring_0_tasks": ["购买"], "user_flows": [], "domains": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "closures": []}

    seam = {"seam_id": "S-1", "status": "frozen", "acceptance_criteria": ["API returns JSON"], "artifacts": []}
    seam_result = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}])
    assert seam_result.compliant is False

    state = acceptance_and_gap_check_node(state, acceptance_goals=["购买流程完整"], work_package_results=[{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}], llm_client=llm)
    assert state.acceptance_verdict["is_production_ready"] is False
    assert state.termination_signal is not True
    assert state.replan_reason is not None
    assert "acceptance" in state.replan_reason
