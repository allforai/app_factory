"""Pre-dispatch granularity validation with split/merge suggestions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..state.work_package import WorkPackage
from .capabilities import get_executor_capability


@dataclass(slots=True)
class GranularityAction:
    action: Literal["ok", "split", "merge"]
    reason: str
    estimated_tokens: int


_LIST_ITEM_OVERHEAD = 50  # approximate chars of structure overhead per list item


def estimate_package_tokens(wp: WorkPackage) -> int:
    """Rough token estimate from goal, title, criteria, constraints, deliverables, inputs, and handoff notes.

    Uses raw character count plus a small structural overhead per list item as a
    proxy for tokens (~1 token per char for compact representation).  This is
    intentionally coarse; the goal is a fast, conservative upper bound.
    """
    scalar_chars = len(wp.goal or "") + len(wp.title or "")

    list_fields: list[list[str]] = [
        wp.acceptance_criteria,
        wp.constraints,
        wp.deliverables,
        wp.inputs,
        wp.handoff_notes,
    ]
    list_chars = sum(len(item) for lst in list_fields for item in lst)
    item_count = sum(len(lst) for lst in list_fields)

    total = scalar_chars + list_chars + item_count * _LIST_ITEM_OVERHEAD
    return max(1, total)


def validate_granularity(wp: WorkPackage, executor_name: str) -> GranularityAction:
    """Check if a work package fits the executor's granularity requirements."""
    cap = get_executor_capability(executor_name)
    tokens = estimate_package_tokens(wp)

    if tokens > cap.max_package_tokens:
        return GranularityAction(
            action="split",
            reason=(
                f"Estimated {tokens} tokens exceeds {executor_name} max "
                f"of {cap.max_package_tokens} tokens"
            ),
            estimated_tokens=tokens,
        )

    merge_threshold = cap.max_package_tokens * 0.05
    if cap.granularity == "coarse" and tokens < merge_threshold:
        return GranularityAction(
            action="merge",
            reason=(
                f"Estimated {tokens} tokens is below merge threshold "
                f"({merge_threshold:.0f}) for coarse executor {executor_name}"
            ),
            estimated_tokens=tokens,
        )

    return GranularityAction(action="ok", reason="", estimated_tokens=tokens)


def suggest_split(wp: WorkPackage, target_count: int = 2) -> list[WorkPackage]:
    """Split a work package by deliverables into target_count pieces."""
    deliverables = list(wp.deliverables)
    acceptance_criteria = list(wp.acceptance_criteria)

    # Distribute deliverables across target_count buckets
    buckets: list[list[str]] = [[] for _ in range(target_count)]
    for i, d in enumerate(deliverables):
        buckets[i % target_count].append(d)

    # Distribute acceptance criteria similarly
    criteria_buckets: list[list[str]] = [[] for _ in range(target_count)]
    for i, c in enumerate(acceptance_criteria):
        criteria_buckets[i % target_count].append(c)

    splits: list[WorkPackage] = []
    for idx in range(target_count):
        split_id = f"{wp.work_package_id}-split-{idx + 1}"
        split_deliverables = buckets[idx] if buckets[idx] else list(wp.deliverables)
        split_criteria = criteria_buckets[idx] if criteria_buckets[idx] else list(wp.acceptance_criteria)

        split_wp = WorkPackage(
            work_package_id=split_id,
            initiative_id=wp.initiative_id,
            project_id=wp.project_id,
            phase=wp.phase,
            domain=wp.domain,
            role_id=wp.role_id,
            title=f"{wp.title} (part {idx + 1}/{target_count})",
            goal=f"{wp.goal} [part {idx + 1}]",
            status="proposed",
            priority=wp.priority,
            executor=wp.executor,
            fallback_executors=list(wp.fallback_executors),
            inputs=list(wp.inputs),
            deliverables=split_deliverables,
            constraints=list(wp.constraints),
            acceptance_criteria=split_criteria,
            depends_on=list(wp.depends_on),
            blocks=list(wp.blocks),
            related_seams=list(wp.related_seams),
            handoff_notes=list(wp.handoff_notes),
            derivation_ring=wp.derivation_ring,
            backfill_source=wp.work_package_id,
        )
        splits.append(split_wp)

    return splits


def suggest_merge(wps: list[WorkPackage]) -> WorkPackage:
    """Merge multiple small work packages into one."""
    if not wps:
        raise ValueError("Cannot merge an empty list of work packages")

    base = wps[0]
    merged_id = "merged-" + "-".join(wp.work_package_id for wp in wps)

    combined_goal = "; ".join(wp.goal for wp in wps)
    combined_deliverables: list[str] = []
    combined_criteria: list[str] = []
    combined_constraints: list[str] = []
    combined_inputs: list[str] = []
    combined_handoff: list[str] = []
    combined_depends_on: list[str] = []
    combined_blocks: list[str] = []
    combined_seams: list[str] = []

    seen_deliverables: set[str] = set()
    seen_criteria: set[str] = set()
    seen_constraints: set[str] = set()

    for wp in wps:
        for d in wp.deliverables:
            if d not in seen_deliverables:
                combined_deliverables.append(d)
                seen_deliverables.add(d)
        for c in wp.acceptance_criteria:
            if c not in seen_criteria:
                combined_criteria.append(c)
                seen_criteria.add(c)
        for c in wp.constraints:
            if c not in seen_constraints:
                combined_constraints.append(c)
                seen_constraints.add(c)
        combined_inputs.extend(wp.inputs)
        combined_handoff.extend(wp.handoff_notes)
        combined_depends_on.extend(wp.depends_on)
        combined_blocks.extend(wp.blocks)
        combined_seams.extend(wp.related_seams)

    return WorkPackage(
        work_package_id=merged_id,
        initiative_id=base.initiative_id,
        project_id=base.project_id,
        phase=base.phase,
        domain=base.domain,
        role_id=base.role_id,
        title=f"Merged: {base.title} (+{len(wps) - 1} more)",
        goal=combined_goal,
        status="proposed",
        priority=base.priority,
        executor=base.executor,
        fallback_executors=list(base.fallback_executors),
        inputs=combined_inputs,
        deliverables=combined_deliverables,
        constraints=combined_constraints,
        acceptance_criteria=combined_criteria,
        depends_on=combined_depends_on,
        blocks=combined_blocks,
        related_seams=combined_seams,
        handoff_notes=combined_handoff,
        derivation_ring=base.derivation_ring,
        backfill_source=None,
    )
