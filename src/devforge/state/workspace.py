"""Workspace state model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class QueueState:
    """Global scheduler queues for the workspace."""

    ready_work: list[str] = field(default_factory=list)
    running_work: list[str] = field(default_factory=list)
    blocked_work: list[str] = field(default_factory=list)
    waiting_input_work: list[str] = field(default_factory=list)
    background_projects: list[str] = field(default_factory=list)
    foreground_project: str | None = None


@dataclass(slots=True)
class WorkspaceState:
    """Top-level operating environment for multiple initiatives and projects."""

    workspace_id: str
    active_initiative_id: str | None = None
    active_project_id: str | None = None
    initiatives: dict[str, str] = field(default_factory=dict)
    projects: dict[str, str] = field(default_factory=dict)
    work_packages: dict[str, str] = field(default_factory=dict)
    seams: dict[str, str] = field(default_factory=dict)
    requirement_events: dict[str, str] = field(default_factory=dict)
    executor_policies: dict[str, str] = field(default_factory=dict)
    executor_registry: dict[str, str] = field(default_factory=dict)
    shared_memory_ref: str | None = None
    scheduler_state: QueueState = field(default_factory=QueueState)
