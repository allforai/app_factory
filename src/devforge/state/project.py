"""Project state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .common import Assumption

ProjectStatus = Literal["active", "blocked", "waiting_input", "split_pending", "split_done", "archived"]


@dataclass(slots=True)
class ProjectArtifacts:
    """Artifact references owned by a project."""

    repo_paths: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProjectState:
    """A project execution unit under one initiative."""

    project_id: str
    initiative_id: str
    parent_project_id: str | None
    name: str
    kind: str
    status: ProjectStatus
    current_phase: str
    phases: list[str] = field(default_factory=list)
    project_archetype: str = ""
    domains: list[str] = field(default_factory=list)
    active_roles: list[str] = field(default_factory=list)
    concept_model_refs: list[str] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    pull_policy_overrides: list[dict[str, object]] = field(default_factory=list)
    llm_preferences: dict[str, object] = field(default_factory=dict)
    knowledge_preferences: dict[str, object] = field(default_factory=dict)
    executor_policy_ref: str | None = None
    work_package_ids: list[str] = field(default_factory=list)
    seam_ids: list[str] = field(default_factory=list)
    artifacts: ProjectArtifacts = field(default_factory=ProjectArtifacts)
    project_memory_ref: str | None = None
    assumptions: list[Assumption] = field(default_factory=list)
    requirement_events: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    coordination_project: bool = False
    created_at: str | None = None
    updated_at: str | None = None
