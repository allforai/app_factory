"""Acceptance and gap data models for production-readiness evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class GoalCheckResult:
    """Result of evaluating a single project goal against delivered functionality."""

    goal: str
    status: Literal["met", "partial", "unmet"]
    reason: str


@dataclass(slots=True)
class ClosureDensityScore:
    """Measures how well ring-0 (critical) closure items have been covered."""

    total_ring_0: int
    covered: int
    coverage_ratio: float


@dataclass(slots=True)
class GapItem:
    """Represents a specific gap identified during acceptance evaluation."""

    gap_id: str
    description: str
    severity: Literal["high", "medium", "low"]
    attributed_domain: str
    attributed_capability: str
    remediation_target: Literal["design", "decomposition", "implementation", "testing"]


@dataclass(slots=True)
class RemediationPackage:
    """A concrete remediation action targeting a specific gap."""

    remediation_id: str
    gap_id: str
    action: Literal["redesign", "reimplement", "add_test", "add_feature", "fix_seam"]
    target_phase: str
    description: str
    affected_work_packages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AcceptanceVerdict:
    """Aggregated acceptance verdict for a project cycle."""

    verdict_id: str
    project_id: str
    cycle_id: str
    is_production_ready: bool
    overall_score: float
    goal_checks: list[GoalCheckResult] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    closure_density: ClosureDensityScore | None = None
    role_evaluations: dict[str, str] = field(default_factory=dict)
    remediations: list[RemediationPackage] = field(default_factory=list)
    summary: str = ""
