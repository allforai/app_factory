"""Tests for gap_analyzer: attribution and remediation package generation."""
from __future__ import annotations

import pytest

from devforge.state.acceptance import (
    AcceptanceVerdict,
    GapItem,
    GoalCheckResult,
    RemediationPackage,
)
from devforge.planning.gap_analyzer import (
    GapAnalysisResult,
    analyze_gaps,
    attribute_gap_to_domain,
    generate_remediations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gap(
    gap_id: str,
    remediation_target: str,
    severity: str = "medium",
) -> GapItem:
    return GapItem(
        gap_id=gap_id,
        description="test gap",
        severity=severity,  # type: ignore[arg-type]
        attributed_domain="",
        attributed_capability="",
        remediation_target=remediation_target,  # type: ignore[arg-type]
    )


def _make_verdict(gaps: list[GapItem], is_ready: bool = False) -> AcceptanceVerdict:
    return AcceptanceVerdict(
        verdict_id="v-1",
        project_id="proj-1",
        cycle_id="c-1",
        is_production_ready=is_ready,
        overall_score=0.5,
        gaps=gaps,
    )


# ---------------------------------------------------------------------------
# test_attribute_design_gap
# ---------------------------------------------------------------------------

def test_attribute_design_gap() -> None:
    gap = _make_gap("g-1", "design")
    result = attribute_gap_to_domain(gap)

    assert result.attributed_domain == "#2"
    assert result.attributed_capability == "产品设计"


# ---------------------------------------------------------------------------
# test_attribute_implementation_gap
# ---------------------------------------------------------------------------

def test_attribute_implementation_gap() -> None:
    gap = _make_gap("g-2", "implementation")
    result = attribute_gap_to_domain(gap)

    assert result.attributed_domain in ("#4", "#5", "#6")
    assert result.attributed_capability  # non-empty


# ---------------------------------------------------------------------------
# test_generate_remediations
# ---------------------------------------------------------------------------

def test_generate_remediations() -> None:
    gaps = [
        _make_gap("g-1", "design"),
        _make_gap("g-2", "testing"),
    ]
    remediations = generate_remediations(gaps, project_id="proj-42")

    assert len(remediations) == 2

    r_design = next(r for r in remediations if r.gap_id == "g-1")
    assert r_design.action == "redesign"

    r_test = next(r for r in remediations if r.gap_id == "g-2")
    assert r_test.action == "add_test"

    # Each remediation must have a non-empty target_phase
    for r in remediations:
        assert r.target_phase


# ---------------------------------------------------------------------------
# test_analyze_gaps_from_verdict
# ---------------------------------------------------------------------------

def test_analyze_gaps_from_verdict() -> None:
    gaps = [
        _make_gap("g-1", "design", severity="high"),
        _make_gap("g-2", "testing", severity="low"),
    ]
    verdict = _make_verdict(gaps)
    analysis = analyze_gaps(verdict)

    # attributed_gaps must be populated
    assert len(analysis.attributed_gaps) == 2
    for ag in analysis.attributed_gaps:
        assert ag.attributed_domain
        assert ag.attributed_capability

    # remediations must be populated
    assert len(analysis.remediations) == 2

    # reentry_point driven by highest-severity gap (design → "product_design")
    assert analysis.reentry_point == "product_design"
