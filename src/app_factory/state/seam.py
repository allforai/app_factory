"""Seam and contract models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SeamStatus = Literal["draft", "reviewing", "frozen", "implemented", "verified", "broken", "deprecated"]


@dataclass(slots=True)
class SeamRisk:
    """A structured seam risk item."""

    id: str
    text: str
    severity: str


@dataclass(slots=True)
class SeamChange:
    """Versioned record of seam contract changes."""

    version: str
    summary: str


@dataclass(slots=True)
class SeamState:
    """Contract and coordination state between split projects."""

    seam_id: str
    initiative_id: str
    source_project_id: str
    target_project_id: str
    type: str
    name: str
    status: SeamStatus
    contract_version: str
    owner_role_id: str
    owner_executor: str
    artifacts: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    risks: list[SeamRisk] = field(default_factory=list)
    related_work_packages: list[str] = field(default_factory=list)
    change_log: list[SeamChange] = field(default_factory=list)
    verification_refs: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
