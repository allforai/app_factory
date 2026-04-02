"""Tests for seam contract compliance verifier."""
import pytest
from devforge.seams.verifier import (
    SeamViolation,
    SeamComplianceResult,
    verify_seam_compliance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seam(status: str = "frozen", criteria: list[str] | None = None) -> dict:
    s: dict = {"id": "seam-1", "status": status}
    if criteria is not None:
        s["acceptance_criteria"] = criteria
    return s


def _result(status: str = "completed", summary: str = "") -> dict:
    return {"status": status, "summary": summary}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_frozen_seam_with_matching_results_passes():
    """A frozen seam with completed results and no deviation keywords is compliant."""
    seam = _seam("frozen", criteria=["The widget renders correctly"])
    wp_results = [_result("completed", "The widget renders correctly as expected")]

    result = verify_seam_compliance(seam, wp_results)

    assert result.compliant is True
    assert result.skipped is False
    assert result.violations == []
    assert result.seam_id == "seam-1"


def test_frozen_seam_with_no_results_fails():
    """A frozen seam with no wp_results gets a no_implementation violation."""
    seam = _seam("frozen")

    result = verify_seam_compliance(seam, [])

    assert result.compliant is False
    assert result.skipped is False
    violation_types = [v.violation_type for v in result.violations]
    assert "no_implementation" in violation_types


def test_broken_status_when_result_mentions_deviation():
    """A deviation keyword in a summary triggers a contract_deviation violation."""
    seam = _seam("implemented")
    wp_results = [_result("completed", "deviation from contract detected in auth flow")]

    result = verify_seam_compliance(seam, wp_results)

    assert result.compliant is False
    violation_types = [v.violation_type for v in result.violations]
    assert "contract_deviation" in violation_types


def test_non_frozen_seam_skipped():
    """A seam with draft status is skipped — compliant=True, skipped=True."""
    seam = _seam("draft")

    result = verify_seam_compliance(seam, [])

    assert result.compliant is True
    assert result.skipped is True
    assert result.violations == []


def test_failed_result_means_seam_not_verified():
    """Any wp_result with status 'failed' triggers an implementation_failed violation."""
    seam = _seam("verified")
    wp_results = [_result("failed", "build step crashed")]

    result = verify_seam_compliance(seam, wp_results)

    assert result.compliant is False
    violation_types = [v.violation_type for v in result.violations]
    assert "implementation_failed" in violation_types


def test_multiple_criteria_partial_compliance():
    """When only some acceptance criteria are met the seam is not compliant."""
    seam = _seam(
        "frozen",
        criteria=[
            "Authentication works",      # key terms: "Authentication", "works"
            "Data persists correctly",   # key terms: "Data", "persists", "correctly"
            "Logging captures events",   # key terms: "Logging", "captures", "events"
        ],
    )
    # Summary covers criterion 1 and 3 but not "persists" or "correctly"
    wp_results = [
        _result("completed", "Authentication works as expected and Logging captures events properly")
    ]

    result = verify_seam_compliance(seam, wp_results)

    assert result.compliant is False
    assert result.criteria_total == 3
    assert result.criteria_met > 0
    assert result.criteria_met < result.criteria_total
    violation_types = [v.violation_type for v in result.violations]
    assert "criteria_unmet" in violation_types
