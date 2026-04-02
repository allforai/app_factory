"""Retry policy resolution for failed work package executions."""

from __future__ import annotations

from typing import Any


def resolve_retry_action(
    work_package: dict[str, Any],
    result: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the retry action for a failed result.

    Actions:
    - ``final_fail``: keep the work package failed
    - ``requeue``: set work package back to ready with same executor
    - ``switch_executor``: set work package back to ready and switch executor
    """

    attempt_count = work_package.get("attempt_count", 0)
    max_attempts = work_package.get("max_attempts", 1)
    if attempt_count >= max_attempts:
        return {"action": "final_fail", "reason": "attempt_limit_reached"}

    context = context or {}
    current_executor = result.get("execution_ref", {}).get("executor") or work_package.get("executor")
    summary = (result.get("summary") or "").lower()
    fallbacks = work_package.get("fallback_executors", [])

    if context.get("requirement_patch_applied"):
        return {"action": "replan", "reason": "requirement_context_changed"}

    if "seam" in summary or "contract" in summary:
        return {"action": "block", "reason": "seam_or_contract_issue"}

    if "rejected" in summary:
        for fallback in fallbacks:
            if fallback != current_executor:
                return {
                    "action": "switch_executor",
                    "reason": "unsupported_by_executor",
                    "next_executor": fallback,
                }

    return {"action": "requeue", "reason": "retry_allowed"}
