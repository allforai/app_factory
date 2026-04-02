"""Tests for acceptance and gap data models."""
import pytest
from devforge.state.acceptance import (
    AcceptanceVerdict,
    ClosureDensityScore,
    GapItem,
    GoalCheckResult,
    RemediationPackage,
)


def test_acceptance_verdict_production_ready():
    """Create a full verdict and verify fields."""
    goal_check = GoalCheckResult(
        goal="User can log in",
        status="met",
        reason="Login flow implemented and tested",
    )
    gap = GapItem(
        gap_id="gap-001",
        description="Missing rate limiting on login endpoint",
        severity="medium",
        attributed_domain="auth",
        attributed_capability="login",
        remediation_target="implementation",
    )
    closure = ClosureDensityScore(total_ring_0=10, covered=9, coverage_ratio=0.9)
    remediation = RemediationPackage(
        remediation_id="rem-001",
        gap_id="gap-001",
        action="reimplement",
        target_phase="implementation",
        description="Add rate limiting middleware",
        affected_work_packages=["wp-003"],
    )
    verdict = AcceptanceVerdict(
        verdict_id="v-001",
        project_id="proj-123",
        cycle_id="cycle-1",
        is_production_ready=True,
        overall_score=0.9,
        goal_checks=[goal_check],
        gaps=[gap],
        closure_density=closure,
        role_evaluations={"architect": "approved", "qa": "approved"},
        remediations=[remediation],
        summary="System meets production requirements",
    )

    assert verdict.verdict_id == "v-001"
    assert verdict.project_id == "proj-123"
    assert verdict.cycle_id == "cycle-1"
    assert verdict.is_production_ready is True
    assert verdict.overall_score == 0.9
    assert len(verdict.goal_checks) == 1
    assert verdict.goal_checks[0].goal == "User can log in"
    assert len(verdict.gaps) == 1
    assert verdict.closure_density is not None
    assert verdict.closure_density.coverage_ratio == 0.9
    assert verdict.role_evaluations["architect"] == "approved"
    assert len(verdict.remediations) == 1
    assert verdict.summary == "System meets production requirements"


def test_gap_item():
    """Create a gap and check attributed_domain and remediation_target."""
    gap = GapItem(
        gap_id="gap-002",
        description="No integration tests for payment flow",
        severity="high",
        attributed_domain="payments",
        attributed_capability="checkout",
        remediation_target="testing",
    )

    assert gap.attributed_domain == "payments"
    assert gap.remediation_target == "testing"
    assert gap.severity == "high"
    assert gap.gap_id == "gap-002"


def test_remediation_package():
    """Create a remediation package and check action and affected_work_packages."""
    pkg = RemediationPackage(
        remediation_id="rem-002",
        gap_id="gap-003",
        action="add_test",
        target_phase="testing",
        description="Add integration tests for checkout",
    )

    assert pkg.action == "add_test"
    assert pkg.affected_work_packages == []

    pkg_with_wps = RemediationPackage(
        remediation_id="rem-003",
        gap_id="gap-003",
        action="add_feature",
        target_phase="implementation",
        description="Implement missing feature",
        affected_work_packages=["wp-001", "wp-002"],
    )

    assert pkg_with_wps.action == "add_feature"
    assert pkg_with_wps.affected_work_packages == ["wp-001", "wp-002"]


def test_goal_check_statuses():
    """Verify all 3 statuses work for GoalCheckResult."""
    met = GoalCheckResult(goal="Goal A", status="met", reason="Fully implemented")
    partial = GoalCheckResult(
        goal="Goal B", status="partial", reason="Partially implemented"
    )
    unmet = GoalCheckResult(goal="Goal C", status="unmet", reason="Not implemented")

    assert met.status == "met"
    assert partial.status == "partial"
    assert unmet.status == "unmet"


def test_acceptance_verdict_defaults():
    """Verify AcceptanceVerdict default fields are properly initialized."""
    verdict = AcceptanceVerdict(
        verdict_id="v-002",
        project_id="proj-456",
        cycle_id="cycle-2",
        is_production_ready=False,
        overall_score=0.3,
    )

    assert verdict.goal_checks == []
    assert verdict.gaps == []
    assert verdict.closure_density is None
    assert verdict.role_evaluations == {}
    assert verdict.remediations == []
    assert verdict.summary == ""
