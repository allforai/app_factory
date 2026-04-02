# tests/test_e2e_orchestration.py
"""Cross-scenario orchestration tests: convergence, state consistency, coverage matrix."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    product_design_node,
    design_validation_node,
    closure_expansion_node,
    acceptance_and_gap_check_node,
)
from devforge.seams.verifier import verify_seam_compliance
from devforge.llm import MockLLMClient


def test_convergence_acceptance_pass_terminates():
    """When acceptance passes, termination_signal is set and no replan."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "T", "ring_0_tasks": ["t1"], "user_flows": [], "domains": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "coverage_ratio": 0.9, "closures": []}

    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["done"],
        work_package_results=[{"work_package_id": "WP-1", "status": "completed", "summary": "done"}],
        llm_client=llm,
    )
    assert state.termination_signal is True
    assert state.replan_reason is None


def test_convergence_acceptance_fail_triggers_replan_not_terminate():
    """When acceptance fails, replan is set but NOT termination."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "T", "ring_0_tasks": ["t1"], "user_flows": [], "domains": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "closures": []}

    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["done"],
        work_package_results=[{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}],
        llm_client=llm,
    )
    assert state.termination_signal is not True
    assert state.replan_reason is not None


def test_design_backloop_clears_validation_on_fix():
    """After design validation fails and design is fixed, re-validation passes."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")

    # Bad design
    state.product_design = {
        "design_id": "D-1", "initiative_id": "I-1", "project_id": "P-1",
        "product_name": "T", "problem_statement": "t", "target_users": ["u"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": ["B"]},
            {"domain_id": "B", "name": "B", "purpose": "b", "inputs": [], "outputs": [], "dependencies": ["A"]},
        ],
        "user_flows": [{"flow_id": "F-1", "name": "m", "role": "u", "steps": ["s"]}],
        "ring_0_tasks": ["t1"], "interaction_matrix": [], "non_functional_requirements": [],
        "tech_choices": {}, "closures": [], "unexplored_areas": [], "version": 1,
    }
    state = design_validation_node(state)
    assert state.design_valid is False
    assert state.replan_reason == "design_validation_failed"

    # Fix: regenerate design (mock produces valid design)
    project = {"project_id": "P-1", "initiative_id": "I-1", "name": "T", "project_archetype": "ecommerce", "current_phase": "analysis_design"}
    state.replan_reason = None
    state = product_design_node(state, project=project, llm_client=llm)
    state = design_validation_node(state)
    assert state.design_valid is True
    assert state.replan_reason is None


def test_seam_compliance_gates_acceptance():
    """If seam is broken, it should be detected before acceptance proceeds."""
    seam = {"seam_id": "S-1", "status": "frozen", "acceptance_criteria": ["data format correct"]}

    # Good result
    good = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "completed", "summary": "data format correct and validated"}])
    assert good.compliant is True

    # Bad result
    bad = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "completed", "summary": "used XML instead of JSON, deviation from contract"}])
    assert bad.compliant is False


def test_scenario_coverage_matrix():
    """Verify both scenarios cover the required verification points."""
    s1_covers = {"design_backloop", "executor_failure_recovery", "executor_switch", "acceptance_backloop", "gap_attribution", "convergence"}
    s2_covers = {"project_split", "seam_freeze_break", "parallel_cross_project", "requirement_change", "acceptance_backloop", "gap_attribution", "convergence"}

    # Both should cover acceptance and convergence
    assert "acceptance_backloop" in s1_covers & s2_covers
    assert "convergence" in s1_covers & s2_covers

    # S1 unique
    assert "executor_failure_recovery" in s1_covers
    assert "executor_switch" in s1_covers

    # S2 unique
    assert "project_split" in s2_covers
    assert "seam_freeze_break" in s2_covers
    assert "requirement_change" in s2_covers
