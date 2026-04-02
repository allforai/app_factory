"""Models for on-demand context pulling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResolvedContext:
    """One resolved context item returned by the broker."""

    ref: str
    kind: str
    mode: str
    title: str = ""
    content: str = ""
    structured: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextPullManifest:
    """Manifest sent to executors so they can pull more context on demand."""

    refs: list[str] = field(default_factory=list)
    preview: list[dict[str, Any]] = field(default_factory=list)
