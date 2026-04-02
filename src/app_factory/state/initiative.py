"""Initiative state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

InitiativeStatus = Literal["active", "blocked", "in_review", "completed", "archived"]


@dataclass(slots=True)
class InitiativeState:
    """Top-level business objective containing one or more projects."""

    initiative_id: str
    name: str
    goal: str
    status: InitiativeStatus
    project_ids: list[str] = field(default_factory=list)
    shared_concepts: list[str] = field(default_factory=list)
    shared_contracts: list[str] = field(default_factory=list)
    initiative_memory_ref: str | None = None
    global_acceptance_goals: list[str] = field(default_factory=list)
    requirement_event_ids: list[str] = field(default_factory=list)
    scheduler_state: dict[str, object] = field(default_factory=dict)
