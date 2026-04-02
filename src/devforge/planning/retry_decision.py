"""Guardrail + LLM-style retry decision interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.llm import LLMClient, MockLLMClient, StructuredGenerationRequest, build_task_llm_client

from .retry_policy import resolve_retry_action


RetryAction = str


@dataclass(slots=True)
class RetryGuardrail:
    """Hard execution bounds that the semantic decider must obey."""

    allowed_actions: list[RetryAction] = field(default_factory=list)
    forbidden_actions: list[RetryAction] = field(default_factory=list)
    hard_blockers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetryDecision:
    """Normalized retry decision produced for orchestration runtime."""

    action: RetryAction
    reason: str
    source: str
    confidence: float = 1.0
    next_executor: str | None = None
    notes: list[str] = field(default_factory=list)


def build_retry_guardrail(
    work_package: dict[str, Any],
    result: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> RetryGuardrail:
    """Build hard bounds for retry decisions.

    These are deterministic system constraints; semantic logic can only choose within them.
    """

    context = context or {}
    allowed = ["final_fail", "requeue", "switch_executor", "block", "replan"]
    forbidden: list[str] = []
    hard_blockers: list[str] = []

    if work_package.get("attempt_count", 0) >= work_package.get("max_attempts", 1):
        allowed = ["final_fail"]
        hard_blockers.append("attempt_limit_reached")

    if context.get("requirement_patch_applied"):
        forbidden.extend(["requeue", "switch_executor"])

    summary = (result.get("summary") or "").lower()
    if "seam" in summary or "contract" in summary:
        forbidden.extend(["requeue", "switch_executor"])
        if "block" not in allowed:
            allowed.append("block")
        hard_blockers.append("seam_or_contract_issue")

    if work_package.get("fallback_executors"):
        if "switch_executor" not in allowed:
            allowed.append("switch_executor")
    else:
        forbidden.append("switch_executor")

    deduped_allowed = [action for i, action in enumerate(allowed) if action not in allowed[:i] and action not in forbidden]
    deduped_forbidden = [action for i, action in enumerate(forbidden) if action not in forbidden[:i]]
    deduped_blockers = [item for i, item in enumerate(hard_blockers) if item not in hard_blockers[:i]]
    return RetryGuardrail(
        allowed_actions=deduped_allowed,
        forbidden_actions=deduped_forbidden,
        hard_blockers=deduped_blockers,
    )


def llm_retry_decider(
    work_package: dict[str, Any],
    result: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> RetryDecision:
    """Stub semantic retry decider.

    This is the future handoff point for a model call. For now it uses current heuristic policy,
    but returns a structured decision that looks like an LLM output.
    """

    context = context or {}
    llm_client = llm_client or build_task_llm_client(task="retry_decision", preferences=llm_preferences) or MockLLMClient()
    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="retry_decision",
            schema_name="RetryDecision",
            instructions=(
                "Decide whether orchestration should requeue, switch executor, block, replan, or final_fail. "
                "Use project-specialized knowledge, node context, seam state, requirement events, and execution history."
            ),
            input_payload={
                "work_package": work_package,
                "result": result,
                "context": context,
            },
            metadata={"decision_kind": "retry"},
        )
    )
    output = response.output
    return RetryDecision(
        action=output["action"],
        reason=output["reason"],
        source=f"{response.provider}:{response.model}",
        confidence=float(output.get("confidence", 0.72)),
        next_executor=output.get("next_executor"),
        notes=list(output.get("notes", [])),
    )


def decide_retry_action(
    work_package: dict[str, Any],
    result: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> RetryDecision:
    """Resolve a final retry decision using guardrails plus semantic decision making."""

    guardrail = build_retry_guardrail(work_package, result, context=context)
    semantic = llm_retry_decider(
        work_package,
        result,
        context=context,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )

    if semantic.action in guardrail.forbidden_actions or semantic.action not in guardrail.allowed_actions:
        fallback = resolve_retry_action(work_package, result, context=context)
        return RetryDecision(
            action=fallback["action"],
            reason=fallback["reason"],
            source="guardrail_fallback",
            confidence=1.0,
            next_executor=fallback.get("next_executor"),
            notes=[f"semantic action {semantic.action!r} not allowed by guardrail"],
        )

    return semantic
