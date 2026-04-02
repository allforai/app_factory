"""LLM-backed concept collection decision interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.llm import LLMClient, MockLLMClient, StructuredGenerationRequest, build_task_llm_client


@dataclass(slots=True)
class ConceptCollectionDecision:
    """Normalized concept collection decision for one orchestration cycle."""

    phase: str | None = None
    goal: str | None = None
    focus_areas: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    rationale: str = ""
    source: str = "unknown"
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)


def llm_concept_collection_decider(
    *,
    project: dict[str, Any],
    selected_knowledge: list[str],
    specialized_knowledge: dict[str, Any],
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> ConceptCollectionDecision:
    """Use the provider-agnostic LLM client to shape one concept collection decision."""

    llm_client = llm_client or build_task_llm_client(task="concept_collection", preferences=llm_preferences) or MockLLMClient()
    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="concept_collection",
            schema_name="ConceptCollectionDecision",
            instructions=(
                "You are a product manager deciding what concept information to collect for a software project. "
                "Based on the project archetype, current phase, and knowledge context, decide the next concept collection step. "
                "Return JSON with these exact fields:\n"
                '- "phase": (string) current development phase, e.g. "concept_collect"\n'
                '- "goal": (string) one-sentence goal for this collection round\n'
                '- "focus_areas": (array of strings) 3-5 key areas to investigate\n'
                '- "questions": (array of strings) 2-4 specific questions to ask\n'
                '- "required_artifacts": (array of strings) artifacts to produce\n'
                '- "rationale": (string) why these focus areas matter\n'
                '- "confidence": (number 0-1) confidence in this decision\n'
                '- "notes": (array of strings) additional observations\n'
            ),
            input_payload={
                "project": project,
                "selected_knowledge": selected_knowledge,
                "specialized_knowledge": specialized_knowledge,
            },
            metadata={"decision_kind": "concept_collection"},
        )
    )
    output = response.output
    return ConceptCollectionDecision(
        phase=output.get("phase"),
        goal=output.get("goal"),
        focus_areas=list(output.get("focus_areas", [])),
        questions=list(output.get("questions", [])),
        required_artifacts=list(output.get("required_artifacts", [])),
        rationale=output.get("rationale", ""),
        source=f"{response.provider}:{response.model}",
        confidence=float(output.get("confidence", 0.72)),
        notes=list(output.get("notes", [])),
    )
