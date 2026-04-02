"""Gap attribution and remediation package generation."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Sequence

from devforge.state.acceptance import AcceptanceVerdict, GapItem, RemediationPackage

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_TARGET_TO_DOMAIN: dict[str, tuple[str, str]] = {
    "design": ("#2", "产品设计"),
    "decomposition": ("#4", "任务分解"),
    "implementation": ("#6", "执行器调度"),
    "testing": ("#10", "集成缝合验证"),
}

_TARGET_TO_ACTION: dict[str, str] = {
    "design": "redesign",
    "decomposition": "reimplement",
    "implementation": "reimplement",
    "testing": "add_test",
}

_TARGET_TO_REENTRY: dict[str, str] = {
    "design": "product_design",
    "decomposition": "task_decomposition",
    "implementation": "batch_dispatch",
    "testing": "batch_verification",
}

# Maps action → target_phase label
_ACTION_TO_PHASE: dict[str, str] = {
    "redesign": "product_design",
    "reimplement": "implementation",
    "add_test": "verification",
    "add_feature": "implementation",
    "fix_seam": "seam_integration",
}

# Severity ordering (higher index = higher priority)
_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GapAnalysisResult:
    """Result of a full gap analysis pass."""

    attributed_gaps: list[GapItem] = field(default_factory=list)
    remediations: list[RemediationPackage] = field(default_factory=list)
    reentry_point: str = ""


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def attribute_gap_to_domain(gap: GapItem) -> GapItem:
    """Return a copy of *gap* with ``attributed_domain`` and
    ``attributed_capability`` populated from :data:`_TARGET_TO_DOMAIN`.
    """
    domain, capability = _TARGET_TO_DOMAIN.get(gap.remediation_target, ("", ""))
    return GapItem(
        gap_id=gap.gap_id,
        description=gap.description,
        severity=gap.severity,
        attributed_domain=domain,
        attributed_capability=capability,
        remediation_target=gap.remediation_target,
    )


def generate_remediations(
    gaps: Sequence[GapItem],
    project_id: str = "",
) -> list[RemediationPackage]:
    """Build one :class:`RemediationPackage` per gap.

    The ``action`` is resolved from :data:`_TARGET_TO_ACTION` and
    ``target_phase`` from :data:`_ACTION_TO_PHASE`.
    """
    packages: list[RemediationPackage] = []
    for idx, gap in enumerate(gaps):
        action = _TARGET_TO_ACTION.get(gap.remediation_target, "reimplement")
        target_phase = _ACTION_TO_PHASE.get(action, action)
        remediation_id = f"rem-{project_id}-{idx}" if project_id else f"rem-{idx}"
        packages.append(
            RemediationPackage(
                remediation_id=remediation_id,
                gap_id=gap.gap_id,
                action=action,  # type: ignore[arg-type]
                target_phase=target_phase,
                description=f"Remediate gap '{gap.gap_id}': {gap.description}",
            )
        )
    return packages


def analyze_gaps(verdict: AcceptanceVerdict) -> GapAnalysisResult:
    """Attribute all gaps in *verdict*, generate remediations, and determine
    the reentry point from the highest-severity gap.
    """
    attributed = [attribute_gap_to_domain(g) for g in verdict.gaps]
    remediations = generate_remediations(attributed, project_id=verdict.project_id)

    reentry_point = ""
    if attributed:
        highest = max(attributed, key=lambda g: _SEVERITY_ORDER.get(g.severity, 0))
        reentry_point = _TARGET_TO_REENTRY.get(highest.remediation_target, "")

    return GapAnalysisResult(
        attributed_gaps=attributed,
        remediations=remediations,
        reentry_point=reentry_point,
    )
