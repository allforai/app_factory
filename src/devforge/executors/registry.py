"""Executor adapter registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ExecutorAdapter


EXECUTOR_REGISTRY: dict[str, "ExecutorAdapter"] = {}


def register_executor_adapter(adapter: "ExecutorAdapter") -> None:
    """Register an executor adapter instance."""
    EXECUTOR_REGISTRY[adapter.name] = adapter


def get_executor_adapter(name: str) -> "ExecutorAdapter":
    """Return a registered executor adapter."""
    return EXECUTOR_REGISTRY[name]

