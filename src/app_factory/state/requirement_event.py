"""Requirement change event model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RequirementEventType = Literal["add", "modify", "remove", "reprioritize"]
RequirementPatchStatus = Literal["recorded", "analyzing", "planned", "applied", "rejected"]


@dataclass(slots=True)
class RequirementEvent:
    """Structured representation of requirement change."""

    requirement_event_id: str
    initiative_id: str
    project_ids: list[str]
    type: RequirementEventType
    summary: str
    details: str = ""
    source: str = "user"
    impact_level: str = "medium"
    affected_domains: list[str] = field(default_factory=list)
    affected_work_packages: list[str] = field(default_factory=list)
    affected_seams: list[str] = field(default_factory=list)
    patch_status: RequirementPatchStatus = "recorded"
    created_at: str | None = None
    applied_at: str | None = None
