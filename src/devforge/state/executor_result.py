"""Normalized executor result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .common import Finding

ExecutorResultStatus = Literal["completed", "partial", "failed", "blocked", "timed_out"]


@dataclass(slots=True)
class ExecutorResult:
    """Executor-agnostic result returned by adapter implementations."""

    execution_id: str
    executor: str
    work_package_id: str
    cycle_id: str | None
    status: ExecutorResultStatus
    summary: str
    execution_ref: dict[str, str | None] = field(default_factory=dict)
    artifacts_created: list[str] = field(default_factory=list)
    artifacts_modified: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    handoff_notes: list[str] = field(default_factory=list)
    raw_output_ref: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
