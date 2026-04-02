"""Shared state primitives."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Assumption:
    """A working assumption used to avoid unnecessary blocking questions."""

    id: str
    text: str
    confidence: float
    blocking: bool = False


@dataclass(slots=True)
class Finding:
    """A normalized finding from implementation, QA, or acceptance."""

    id: str
    summary: str
    severity: str
    source: str
    details: str = ""
    related_artifacts: list[str] = field(default_factory=list)
