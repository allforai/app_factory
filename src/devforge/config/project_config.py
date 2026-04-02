"""Project-level config loading and snapshot application helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devforge.executors import normalize_pull_policy_overrides


def load_project_config(path: str | Path) -> dict[str, Any]:
    """Load one project config file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def apply_project_config(snapshot: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Apply project-level config overrides onto a snapshot."""

    updated = json.loads(json.dumps(snapshot))
    project_configs = config.get("projects", {})
    for project in updated.get("projects", []):
        override = project_configs.get(project.get("project_id"))
        if not override:
            continue
        if "pull_policy_overrides" in override:
            normalized = normalize_pull_policy_overrides(override["pull_policy_overrides"])
            project["pull_policy_overrides"] = [
                {
                    "executor": rule.executor,
                    "mode": rule.mode,
                    "budget": rule.budget,
                    "ref_patterns": rule.ref_patterns,
                    "role_id": rule.role_id,
                    "phase": rule.phase,
                    "project_archetype": rule.project_archetype,
                }
                for rule in normalized
            ]
        if "llm_preferences" in override:
            project["llm_preferences"] = dict(override["llm_preferences"])
        if "knowledge_preferences" in override:
            project["knowledge_preferences"] = dict(override["knowledge_preferences"])
    return updated


def maybe_apply_fixture_project_config(fixture_root: str | Path, fixture_name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Apply a sibling fixture project config when present."""

    config_path = Path(fixture_root) / f"{fixture_name}.project_config.json"
    if not config_path.exists():
        return snapshot
    return apply_project_config(snapshot, load_project_config(config_path))
