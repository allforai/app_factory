"""Config-style pull policy resolution for executor context loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.state import WorkPackage

ALLOWED_PULL_MODES = {"summary", "structured", "full"}

PULL_POLICY_OVERRIDE_SCHEMA: dict[str, object] = {
    "required": ["executor", "mode"],
    "optional": ["role_id", "phase", "project_archetype", "budget", "ref_patterns"],
    "allowed_modes": sorted(ALLOWED_PULL_MODES),
}


@dataclass(slots=True)
class PullPolicyRule:
    """One pull policy rule scoped by executor, role, and phase."""

    executor: str
    mode: str
    budget: int | None
    ref_patterns: list[str] = field(default_factory=list)
    role_id: str | None = None
    phase: str | None = None
    project_archetype: str | None = None

    def matches(self, *, executor: str, role_id: str, phase: str, project_archetype: str | None = None) -> bool:
        return (
            self.executor == executor
            and (self.role_id is None or self.role_id == role_id)
            and (self.phase is None or self.phase == phase)
            and (self.project_archetype is None or self.project_archetype == project_archetype)
        )

    def select_refs(self, refs: list[str]) -> list[str]:
        if not self.ref_patterns:
            return refs
        selected = [
            ref
            for ref in refs
            if any(
                ref.startswith(pattern)
                or ref.endswith(pattern)
                or pattern in ref
                for pattern in self.ref_patterns
            )
        ]
        return selected or refs


PULL_POLICY_RULES: list[PullPolicyRule] = [
    PullPolicyRule(
        executor="codex",
        role_id="software_engineer",
        phase="implementation",
        project_archetype="game",
        mode="structured",
        budget=None,
        ref_patterns=["project://", "latest-specialized-knowledge", "implementation", "domain.gaming"],
    ),
    PullPolicyRule(
        executor="claude_code",
        role_id="technical_architect",
        mode="summary",
        budget=2400,
        ref_patterns=["project://", "latest-specialized-knowledge", "analysis_design"],
    ),
    PullPolicyRule(
        executor="claude_code",
        role_id="qa_engineer",
        mode="summary",
        budget=1800,
        ref_patterns=["acceptance_goals.json", "concept_brief.md", "testing"],
    ),
    PullPolicyRule(
        executor="claude_code",
        role_id="software_engineer",
        phase="implementation",
        mode="summary",
        budget=2100,
        ref_patterns=["project://", "latest-specialized-knowledge", "implementation"],
    ),
    PullPolicyRule(
        executor="claude_code",
        role_id="software_engineer",
        phase="testing",
        mode="summary",
        budget=1700,
        ref_patterns=["acceptance_goals.json", "concept_brief.md", "testing"],
    ),
    PullPolicyRule(
        executor="codex",
        role_id="technical_architect",
        mode="structured",
        budget=None,
        ref_patterns=["project://", "latest-specialized-knowledge", "analysis_design"],
    ),
    PullPolicyRule(
        executor="codex",
        role_id="qa_engineer",
        mode="structured",
        budget=None,
        ref_patterns=["project://", "acceptance_goals.json", "testing"],
    ),
    PullPolicyRule(
        executor="codex",
        role_id="software_engineer",
        phase="implementation",
        mode="structured",
        budget=None,
        ref_patterns=["project://", "latest-specialized-knowledge", "implementation"],
    ),
    PullPolicyRule(
        executor="codex",
        role_id="software_engineer",
        phase="testing",
        mode="structured",
        budget=None,
        ref_patterns=["project://", "acceptance_goals.json", "testing"],
    ),
]


def resolve_pull_strategy(
    executor: str,
    work_package: WorkPackage,
    refs: list[str],
    *,
    project_archetype: str | None = None,
    override_rules: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Resolve a pull strategy from the local policy registry."""

    rules = list(_normalize_override_rules(override_rules)) + PULL_POLICY_RULES
    for rule in rules:
        if rule.matches(
            executor=executor,
            role_id=work_package.role_id,
            phase=work_package.phase,
            project_archetype=project_archetype,
        ):
            return {
                "mode": rule.mode,
                "budget": rule.budget,
                "refs": rule.select_refs(refs),
            }
    return {
        "mode": "summary",
        "budget": 1200,
        "refs": refs,
    }


def normalize_pull_policy_overrides(items: list[dict[str, object]] | None) -> list[PullPolicyRule]:
    """Validate and normalize project-level override rules."""

    if not items:
        return []
    normalized: list[PullPolicyRule] = []
    for item in items:
        _validate_override_rule(item)
        normalized.append(
            PullPolicyRule(
                executor=str(item["executor"]),
                mode=str(item["mode"]),
                budget=item.get("budget"),
                ref_patterns=[str(pattern) for pattern in item.get("ref_patterns", [])],
                role_id=str(item["role_id"]) if item.get("role_id") is not None else None,
                phase=str(item["phase"]) if item.get("phase") is not None else None,
                project_archetype=str(item["project_archetype"]) if item.get("project_archetype") is not None else None,
            )
        )
    return normalized


def _normalize_override_rules(items: list[dict[str, object]] | None) -> list[PullPolicyRule]:
    return normalize_pull_policy_overrides(items)


def _validate_override_rule(item: dict[str, object]) -> None:
    missing = [key for key in ("executor", "mode") if key not in item]
    if missing:
        raise ValueError(f"pull policy override missing required keys: {missing}")
    mode = str(item["mode"])
    if mode not in ALLOWED_PULL_MODES:
        raise ValueError(f"unsupported pull mode: {mode}")
    budget = item.get("budget")
    if budget is not None and not isinstance(budget, int):
        raise ValueError("pull policy override budget must be an integer or null")
    ref_patterns = item.get("ref_patterns", [])
    if not isinstance(ref_patterns, list):
        raise ValueError("pull policy override ref_patterns must be a list")
