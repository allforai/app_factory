"""Tests for acceptance_and_gap_check_node."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import acceptance_and_gap_check_node
from devforge.llm import MockLLMClient


def test_acceptance_node_production_ready():
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "Test", "ring_0_tasks": ["t1"], "user_flows": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "coverage_ratio": 0.9, "closures": []}
    updated = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["feature complete"],
        work_package_results=[{"work_package_id": "WP-1", "status": "completed", "summary": "done"}],
        llm_client=MockLLMClient(),
    )
    assert updated.acceptance_verdict is not None
    assert updated.acceptance_verdict["is_production_ready"] is True
    assert updated.termination_signal is True


def test_acceptance_node_not_ready_triggers_gap_analysis():
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "Test", "ring_0_tasks": ["t1"], "user_flows": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "closures": []}
    updated = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["feature complete"],
        work_package_results=[{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}],
        llm_client=MockLLMClient(),
    )
    assert updated.acceptance_verdict["is_production_ready"] is False
    assert updated.termination_signal is not True
    assert updated.replan_reason is not None
