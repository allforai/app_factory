"""Work package model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .common import Assumption, Finding

WorkPackageStatus = Literal[
    "proposed",
    "ready",
    "running",
    "blocked",
    "waiting_review",
    "completed",
    "verified",
    "failed",
    "deprecated",
]


@dataclass(slots=True)
class WorkPackage:
    """A bounded execution unit resolved through role and executor policy."""

    work_package_id: str
    initiative_id: str
    project_id: str
    phase: str
    domain: str
    role_id: str
    title: str
    goal: str
    status: WorkPackageStatus
    priority: int = 50
    executor: str | None = None
    fallback_executors: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    related_seams: list[str] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    artifacts_created: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    handoff_notes: list[str] = field(default_factory=list)
    last_execution_ref: dict[str, str | None] = field(default_factory=dict)
    execution_history: list[dict[str, str | None]] = field(default_factory=list)
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: str | None = None
    updated_at: str | None = None
    derivation_ring: int = 0
    backfill_source: str | None = None
