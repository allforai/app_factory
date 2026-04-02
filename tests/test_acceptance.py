"""Tests for LLM-driven acceptance evaluator."""
from __future__ import annotations

import pytest
from devforge.llm import MockLLMClient
from devforge.planning.acceptance import evaluate_acceptance
from devforge.state.acceptance import AcceptanceVerdict


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_ACCEPTANCE_GOALS = [
    "Users can complete checkout",
    "Admin can manage products",
]

_DESIGN_SUMMARY = {
    "product_name": "TestShop",
    "user_flows": [
        {"flow_id": "F-001", "name": "购买流程", "role": "buyer",
         "steps": ["浏览", "结算", "支付"], "entry_point": "首页", "exit_point": "订单页"},
        {"flow_id": "F-002", "name": "发布流程", "role": "seller",
         "steps": ["填写", "发布"], "entry_point": "发布入口", "exit_point": "详情页"},
    ],
    "domains": [{"domain_id": "#11", "name": "交易"}],
}

_CLOSURE_EXPANSION = {
    "total_ring_0": 4,
    "total_ring_1": 8,
    "coverage_ratio": 0.67,
}

_COMPLETED_RESULTS = [
    {"work_package_id": "wp-001", "status": "completed"},
    {"work_package_id": "wp-002", "status": "verified"},
]

_FAILED_RESULTS = [
    {"work_package_id": "wp-001", "status": "completed"},
    {"work_package_id": "wp-002", "status": "failed"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluate_acceptance_returns_verdict():
    """All completed work packages → AcceptanceVerdict with goal_checks and positive score."""
    verdict = evaluate_acceptance(
        project_id="proj-1",
        cycle_id="cycle-1",
        acceptance_goals=_ACCEPTANCE_GOALS,
        work_package_results=_COMPLETED_RESULTS,
        design_summary=_DESIGN_SUMMARY,
        closure_expansion=_CLOSURE_EXPANSION,
        llm_client=MockLLMClient(),
    )

    assert isinstance(verdict, AcceptanceVerdict)
    assert verdict.project_id == "proj-1"
    assert verdict.cycle_id == "cycle-1"
    assert len(verdict.goal_checks) > 0
    assert verdict.overall_score > 0
    assert verdict.is_production_ready is True


def test_evaluate_acceptance_with_failures_not_production_ready():
    """A failed work package → not production ready, gaps present."""
    verdict = evaluate_acceptance(
        project_id="proj-2",
        cycle_id="cycle-2",
        acceptance_goals=_ACCEPTANCE_GOALS,
        work_package_results=_FAILED_RESULTS,
        design_summary=_DESIGN_SUMMARY,
        llm_client=MockLLMClient(),
    )

    assert isinstance(verdict, AcceptanceVerdict)
    assert verdict.is_production_ready is False
    assert len(verdict.gaps) > 0
    assert verdict.gaps[0].severity == "high"
    assert verdict.gaps[0].remediation_target == "implementation"


def test_evaluate_acceptance_includes_role_evaluations():
    """design_summary with user_flows roles → role_evaluations populated in verdict."""
    verdict = evaluate_acceptance(
        project_id="proj-3",
        cycle_id="cycle-3",
        acceptance_goals=_ACCEPTANCE_GOALS,
        work_package_results=_COMPLETED_RESULTS,
        design_summary=_DESIGN_SUMMARY,
        llm_client=MockLLMClient(),
    )

    assert isinstance(verdict.role_evaluations, dict)
    assert len(verdict.role_evaluations) > 0
    # roles from user_flows: buyer, seller
    roles_present = set(verdict.role_evaluations.keys())
    assert "buyer" in roles_present or "seller" in roles_present


def test_evaluate_acceptance_closure_density():
    """closure_expansion data passes through to ClosureDensityScore."""
    verdict = evaluate_acceptance(
        project_id="proj-4",
        cycle_id="cycle-4",
        acceptance_goals=_ACCEPTANCE_GOALS,
        work_package_results=_COMPLETED_RESULTS,
        design_summary=_DESIGN_SUMMARY,
        closure_expansion=_CLOSURE_EXPANSION,
        llm_client=MockLLMClient(),
    )

    assert verdict.closure_density is not None
    assert verdict.closure_density.total_ring_0 == _CLOSURE_EXPANSION["total_ring_0"]
    assert verdict.closure_density.covered == _CLOSURE_EXPANSION["total_ring_1"]
    assert abs(verdict.closure_density.coverage_ratio - _CLOSURE_EXPANSION["coverage_ratio"]) < 0.01
