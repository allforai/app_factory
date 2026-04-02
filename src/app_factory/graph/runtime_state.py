"""LangGraph-oriented runtime state model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeState:
    """Operational state for one orchestration cycle."""

    workspace_id: str
    cycle_id: str | None = None
    initiative_id: str | None = None
    active_project_id: str | None = None
    current_phase: str | None = None
    phase_goal: str | None = None
    foreground_project: str | None = None
    background_projects: list[str] = field(default_factory=list)
    ready_queue: list[str] = field(default_factory=list)
    running_queue: list[str] = field(default_factory=list)
    blocked_queue: list[str] = field(default_factory=list)
    pending_requirement_events: list[str] = field(default_factory=list)
    pending_seam_checks: list[str] = field(default_factory=list)
    current_workset: list[str] = field(default_factory=list)
    selected_knowledge: list[str] = field(default_factory=list)
    project_llm_preferences: dict[str, Any] = field(default_factory=dict)
    project_knowledge_preferences: dict[str, Any] = field(default_factory=dict)
    specialized_knowledge: dict[str, Any] = field(default_factory=dict)
    node_knowledge_packet: dict[str, Any] = field(default_factory=dict)
    concept_decision: dict[str, Any] = field(default_factory=dict)
    planning_decision: dict[str, Any] = field(default_factory=dict)
    recent_executor_results: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] | None = None
    replan_reason: str | None = None
    product_design: dict[str, object] | None = None
    design_valid: bool | None = None
    design_validation_issues: list[dict[str, object]] = field(default_factory=list)
    closure_expansion: dict[str, object] | None = None
    needs_user_input: bool = False
    termination_signal: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeState":
        """Build runtime state from a plain dict."""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert runtime state to a plain dict."""
        return asdict(self)
