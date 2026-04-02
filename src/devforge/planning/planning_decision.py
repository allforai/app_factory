"""LLM-backed planning and shaping decision interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.llm import LLMClient, MockLLMClient, StructuredGenerationRequest, build_task_llm_client


@dataclass(slots=True)
class PlanningDecision:
    """Normalized planning decision for one orchestration cycle."""

    selected_workset: list[str] = field(default_factory=list)
    phase: str | None = None
    goal: str | None = None
    rationale: str = ""
    source: str = "unknown"
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)


def llm_planning_decider(
    *,
    project: dict[str, Any],
    workset_ids: list[str],
    selected_knowledge: list[str],
    specialized_knowledge: dict[str, Any],
    node_knowledge_packet: dict[str, Any],
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> PlanningDecision:
    """Use the provider-agnostic LLM client to shape one planning decision."""

    llm_client = llm_client or build_task_llm_client(task="planning_and_shaping", preferences=llm_preferences) or MockLLMClient()
    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="planning_and_shaping",
            schema_name="PlanningDecision",
            instructions=(
                "Select the active workset for this cycle and summarize the planning rationale. "
                "Use project archetype, current phase, selected knowledge, and specialized knowledge. "
                "Return only JSON."
            ),
            input_payload={
                "project": project,
                "workset_ids": workset_ids,
                "selected_knowledge": selected_knowledge,
                "specialized_knowledge": specialized_knowledge,
                "node_knowledge_packet": node_knowledge_packet,
            },
            metadata={"decision_kind": "planning"},
        )
    )
    output = response.output
    return PlanningDecision(
        selected_workset=list(output.get("selected_workset", workset_ids)),
        phase=output.get("phase"),
        goal=output.get("goal"),
        rationale=output.get("rationale", ""),
        source=f"{response.provider}:{response.model}",
        confidence=float(output.get("confidence", 0.72)),
        notes=list(output.get("notes", [])),
    )
