"""Tests for ExecutorCapability dataclass and registry."""
from __future__ import annotations

import pytest

from app_factory.executors.capabilities import (
    EXECUTOR_CAPABILITIES,
    ExecutorCapability,
    get_executor_capability,
)


def test_claude_code_capability() -> None:
    cap = EXECUTOR_CAPABILITIES["claude_code"]
    assert cap.context_window > 0
    assert cap.max_package_tokens > 0
    assert cap.granularity == "coarse"
    assert "implementation" in cap.supported_phases


def test_codex_capability() -> None:
    codex_cap = EXECUTOR_CAPABILITIES["codex"]
    claude_cap = EXECUTOR_CAPABILITIES["claude_code"]
    assert codex_cap.granularity == "fine"
    assert codex_cap.max_package_tokens < claude_cap.max_package_tokens


def test_python_capability() -> None:
    cap = EXECUTOR_CAPABILITIES["python"]
    assert cap.granularity == "any"


def test_unknown_executor_returns_default() -> None:
    cap = get_executor_capability("nonexistent_executor")
    assert cap.granularity == "any"


def test_all_registered_executors_have_capabilities() -> None:
    expected_names = {"python", "claude_code", "codex", "cline", "opencode"}
    assert set(EXECUTOR_CAPABILITIES.keys()) == expected_names
    for name in expected_names:
        cap = EXECUTOR_CAPABILITIES[name]
        assert cap.context_window > 0, f"{name} must have context_window > 0"
