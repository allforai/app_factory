"""Base executor adapter interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from devforge.context import ContextBroker, ResolvedContext
from devforge.state import ExecutorResult, WorkPackage


@dataclass(slots=True)
class ExecutorDispatch:
    """Normalized dispatch record returned immediately after task submission."""

    execution_id: str
    executor: str
    work_package_id: str
    accepted: bool
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SubmissionReceipt:
    """Raw submission receipt returned by the executor transport boundary."""

    execution_id: str
    accepted: bool
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CodexTaskRequest:
    """Structured request shape prepared for Codex-style execution."""

    executor: str
    mode: str
    task_type: str
    work_package_id: str
    goal: str
    cycle_id: str | None = None
    deliverables: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClaudeCodeTaskRequest:
    """Structured request shape prepared for Claude Code-style delegation."""

    executor: str
    mode: str
    task_type: str
    work_package_id: str
    goal: str
    cycle_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    references: list[str] = field(default_factory=list)


class ExecutorAdapter(Protocol):
    """Protocol for pluggable executor backends."""

    name: str

    def supports_phase(self, phase: str) -> bool:
        """Return whether this adapter supports the given orchestration phase."""

    def supports_role(self, role_id: str) -> bool:
        """Return whether this adapter supports the given role."""

    def estimate(self, work_package: WorkPackage) -> dict[str, Any]:
        """Return a lightweight planning estimate for scheduling."""

    def prepare_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Prepare an executor-specific request payload before submission."""

    def submit(self, request: dict[str, Any]) -> SubmissionReceipt:
        """Submit a prepared request to the underlying executor transport."""

    def submit_request(self, request: dict[str, Any], *, accepted: bool) -> ExecutorDispatch:
        """Submit a prepared request and return a dispatch record."""

    def dispatch(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> ExecutorDispatch:
        """Dispatch a work package to the underlying executor."""

    def default_pull_strategy(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Return the default pull strategy for this executor and role."""

    def pull_context(
        self,
        refs: list[str],
        *,
        broker: ContextBroker,
        mode: str = "summary",
        budget: int | None = None,
    ) -> list[ResolvedContext]:
        """Resolve additional context through the shared broker."""

    def poll(self, execution_id: str) -> dict[str, Any]:
        """Poll the underlying executor for status."""

    def cancel(self, execution_id: str) -> dict[str, Any]:
        """Cancel an in-flight execution if supported."""

    def normalize_result(self, raw_result: dict[str, Any]) -> ExecutorResult:
        """Convert executor-specific output into a normalized result."""
