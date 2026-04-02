"""Executor capability metadata for granularity control."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class ExecutorCapability:
    name: str
    context_window: int
    max_package_tokens: int
    granularity: Literal["coarse", "fine", "any"]
    supported_phases: list[str] = field(default_factory=list)
    max_concurrent: int = 1
    supports_streaming: bool = False


EXECUTOR_CAPABILITIES: dict[str, ExecutorCapability] = {
    "python": ExecutorCapability(
        name="python",
        context_window=1_000_000,
        max_package_tokens=100_000,
        granularity="any",
        supported_phases=["concept_collect", "acceptance", "requirement_patch"],
        max_concurrent=10,
    ),
    "claude_code": ExecutorCapability(
        name="claude_code",
        context_window=200_000,
        max_package_tokens=50_000,
        granularity="coarse",
        supported_phases=[
            "concept_collect",
            "analysis_design",
            "implementation",
            "testing",
            "acceptance",
        ],
        max_concurrent=3,
    ),
    "codex": ExecutorCapability(
        name="codex",
        context_window=100_000,
        max_package_tokens=15_000,
        granularity="fine",
        supported_phases=["analysis_design", "implementation", "testing"],
        max_concurrent=5,
    ),
    "cline": ExecutorCapability(
        name="cline",
        context_window=100_000,
        max_package_tokens=20_000,
        granularity="fine",
        supported_phases=["implementation", "testing"],
        max_concurrent=2,
    ),
    "opencode": ExecutorCapability(
        name="opencode",
        context_window=100_000,
        max_package_tokens=20_000,
        granularity="fine",
        supported_phases=["analysis_design"],
        max_concurrent=2,
    ),
}

_DEFAULT_CAPABILITY = ExecutorCapability(
    name="default",
    context_window=50_000,
    max_package_tokens=10_000,
    granularity="any",
    supported_phases=[],
    max_concurrent=1,
)


def get_executor_capability(executor_name: str) -> ExecutorCapability:
    return EXECUTOR_CAPABILITIES.get(executor_name, _DEFAULT_CAPABILITY)
