"""Executor selection policy models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutorPolicy:
    """Layered executor resolution policy."""

    policy_id: str
    default: str
    by_phase: dict[str, str] = field(default_factory=dict)
    by_role: dict[str, str] = field(default_factory=dict)
    by_domain: dict[str, str] = field(default_factory=dict)
    by_work_package: dict[str, str] = field(default_factory=dict)
    fallback_order: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    def resolve(self, *, work_package_id: str, domain: str, role_id: str, phase: str) -> str:
        """Resolve the selected executor using the documented precedence."""
        if work_package_id in self.by_work_package:
            return self.by_work_package[work_package_id]
        if domain in self.by_domain:
            return self.by_domain[domain]
        if role_id in self.by_role:
            return self.by_role[role_id]
        if phase in self.by_phase:
            return self.by_phase[phase]
        return self.default
