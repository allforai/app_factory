"""Role specification models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RoleSpec:
    """Responsibility template used to shape work packages."""

    role_id: str
    name: str
    purpose: str
    capabilities: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    allowed_phases: list[str] = field(default_factory=list)
    preferred_executors: list[str] = field(default_factory=list)
