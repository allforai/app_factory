"""Seam contract compliance verifier."""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = {"frozen", "implemented", "verified"}

_DEVIATION_KEYWORDS = {
    "deviation",
    "diverge",
    "mismatch",
    "incompatible",
    "instead of",
    "differs from",
    "broke",
    "breaking",
}


@dataclass(slots=True)
class SeamViolation:
    violation_type: str
    description: str
    seam_id: str = ""
    work_package_id: str = ""


@dataclass(slots=True)
class SeamComplianceResult:
    seam_id: str
    compliant: bool
    skipped: bool = False
    violations: list[SeamViolation] = field(default_factory=list)
    criteria_met: int = 0
    criteria_total: int = 0


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------

def verify_seam_compliance(
    seam: dict,
    wp_results: list[dict],
) -> SeamComplianceResult:
    """Verify that a seam's contract is upheld by its work-package results.

    Args:
        seam:       Seam definition dict (must have at least ``id`` and ``status``).
        wp_results: List of work-package result dicts, each with ``status`` and
                    optionally ``summary``.

    Returns:
        A :class:`SeamComplianceResult` describing compliance.
    """
    seam_id: str = seam.get("id", "")
    status: str = seam.get("status", "")

    # 1. Skip inactive seams
    if status not in _ACTIVE_STATUSES:
        return SeamComplianceResult(seam_id=seam_id, compliant=True, skipped=True)

    violations: list[SeamViolation] = []

    # 2. No results at all
    if not wp_results:
        violations.append(
            SeamViolation(
                violation_type="no_implementation",
                description="No work-package results found for seam.",
                seam_id=seam_id,
            )
        )
        return SeamComplianceResult(
            seam_id=seam_id,
            compliant=False,
            violations=violations,
        )

    # 3. Any failed results
    for wp in wp_results:
        if wp.get("status") == "failed":
            violations.append(
                SeamViolation(
                    violation_type="implementation_failed",
                    description="One or more work packages failed.",
                    seam_id=seam_id,
                    work_package_id=str(wp.get("id", "")),
                )
            )
            break  # one violation entry is sufficient

    # 4. Deviation keywords in summaries
    combined_summaries = " ".join(
        wp.get("summary", "") for wp in wp_results
    ).lower()

    for keyword in _DEVIATION_KEYWORDS:
        if keyword in combined_summaries:
            violations.append(
                SeamViolation(
                    violation_type="contract_deviation",
                    description=f"Summary contains deviation indicator: '{keyword}'.",
                    seam_id=seam_id,
                )
            )
            break  # one violation entry is sufficient

    # 5. Acceptance criteria coverage
    criteria: list[str] = seam.get("acceptance_criteria", [])
    criteria_met = 0
    criteria_total = len(criteria)

    if criteria_total > 0:
        for criterion in criteria:
            # Extract meaningful words (> 3 chars)
            key_terms = [w.lower() for w in criterion.split() if len(w) > 3]
            if key_terms and any(term in combined_summaries for term in key_terms):
                criteria_met += 1

        if criteria_met < criteria_total:
            violations.append(
                SeamViolation(
                    violation_type="criteria_unmet",
                    description=(
                        f"Only {criteria_met}/{criteria_total} acceptance criteria "
                        "appear to be addressed in the work-package summaries."
                    ),
                    seam_id=seam_id,
                )
            )

    compliant = len(violations) == 0
    return SeamComplianceResult(
        seam_id=seam_id,
        compliant=compliant,
        violations=violations,
        criteria_met=criteria_met,
        criteria_total=criteria_total,
    )
