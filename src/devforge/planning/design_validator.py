"""Structural validator for ProductDesign artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devforge.state.design import ProductDesign


@dataclass(slots=True)
class ValidationIssue:
    """A single validation finding."""

    error_type: str
    message: str
    domain_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    """Aggregated result of a design validation run."""

    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    resolved_issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_cycles(domains: list) -> list[ValidationIssue]:
    """DFS-based cycle detection on domain dependencies.

    Returns one ValidationIssue per cycle found, listing the domain IDs
    that participate in the cycle.
    """
    # Build adjacency map: domain_id -> list[dependency_id]
    adj: dict[str, list[str]] = {d.domain_id: list(d.dependencies) for d in domains}
    known_ids = set(adj.keys())

    # Three-colour DFS: white=0, grey=1 (in stack), black=2 (done)
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {node: WHITE for node in known_ids}
    stack: list[str] = []
    issues: list[ValidationIssue] = []
    reported_cycles: set[frozenset[str]] = set()

    def dfs(node: str) -> None:
        colour[node] = GREY
        stack.append(node)
        for neighbour in adj.get(node, []):
            if neighbour not in known_ids:
                # Dependency references unknown domain — skip for cycle detection
                continue
            if colour[neighbour] == GREY:
                # Found a cycle — extract the cycle nodes from the stack
                cycle_start = stack.index(neighbour)
                cycle_nodes = stack[cycle_start:]
                cycle_key = frozenset(cycle_nodes)
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    issues.append(
                        ValidationIssue(
                            error_type="dependency_cycle",
                            message=(
                                f"Dependency cycle detected among domains: "
                                f"{', '.join(cycle_nodes)}"
                            ),
                            domain_ids=list(cycle_nodes),
                        )
                    )
            elif colour[neighbour] == WHITE:
                dfs(neighbour)
        stack.pop()
        colour[node] = BLACK

    for node in list(known_ids):
        if colour[node] == WHITE:
            dfs(node)

    return issues


def _detect_missing_seams(
    domains: list,
    existing_seam_pairs: set[tuple[str, str]] | None,
) -> list[ValidationIssue]:
    """Warn when a dependency edge has no corresponding seam record.

    Only runs when *existing_seam_pairs* is explicitly provided (not None).
    """
    if existing_seam_pairs is None:
        return []

    issues: list[ValidationIssue] = []
    for domain in domains:
        for dep_id in domain.dependencies:
            pair = (dep_id, domain.domain_id)
            if pair not in existing_seam_pairs:
                issues.append(
                    ValidationIssue(
                        error_type="missing_seam",
                        message=(
                            f"Domain '{domain.domain_id}' depends on '{dep_id}' "
                            f"but no seam exists for that pair."
                        ),
                        domain_ids=[dep_id, domain.domain_id],
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_design(
    design: ProductDesign,
    *,
    existing_seam_pairs: set[tuple[str, str]] | None = None,
    previous_issues: list[str] | None = None,
) -> ValidationResult:
    """Validate the structural integrity of a *ProductDesign*.

    Parameters
    ----------
    design:
        The design artifact to validate.
    existing_seam_pairs:
        A set of ``(provider_id, consumer_id)`` tuples representing seams that
        have already been defined.  When *None*, missing-seam checks are
        skipped.  Pass an empty set to flag all dependency edges as missing.
    previous_issues:
        A list of ``error_type`` strings from a previous validation run.
        Any types that no longer appear as errors in the current run are
        recorded in ``ValidationResult.resolved_issues``.

    Returns
    -------
    ValidationResult
    """
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    # 1. Dependency cycle detection (errors)
    errors.extend(_detect_cycles(design.domains))

    # 2. Missing seam detection (warnings)
    warnings.extend(_detect_missing_seams(design.domains, existing_seam_pairs))

    # 3. Empty ring_0_tasks (error)
    if not design.ring_0_tasks:
        errors.append(
            ValidationIssue(
                error_type="empty_ring_0",
                message="ring_0_tasks must not be empty.",
            )
        )

    # 4. No user_flows (error)
    if not design.user_flows:
        errors.append(
            ValidationIssue(
                error_type="no_user_flows",
                message="Design must define at least one user flow.",
            )
        )

    # 5. Iteration fix tracking
    resolved_issues: list[str] = []
    if previous_issues:
        current_error_types = {e.error_type for e in errors}
        for issue_type in previous_issues:
            if issue_type not in current_error_types:
                resolved_issues.append(issue_type)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        resolved_issues=resolved_issues,
    )
