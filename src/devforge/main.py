"""Minimal entrypoints for running orchestration cycles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from devforge.config import apply_project_config, load_project_config, maybe_apply_fixture_project_config
from devforge.graph.builder import run_cycle
from devforge.llm.config_loader import load_llm_config
from devforge.onboarding import read_readme_excerpt
from devforge.persistence import JsonStore, build_local_workspace_persistence
from devforge.topology import WorkspaceCandidate, default_live_llm_preferences, dump_decision
from devforge.executors import get_executor_adapter

DEFAULT_RUNTIME_ROOT = ".devforge"
DEFAULT_SNAPSHOT_FILENAME = "devforge.snapshot.json"
DEFAULT_PROJECT_CONFIG_FILENAME = "devforge.project_config.json"
WORKSPACE_PROJECT_MARKERS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "Package.swift",
    "Podfile",
    ".git",
)

LLM_SETUP_PRESETS = {"auto", "offline", "live"}
KNOWLEDGE_SETUP_PRESETS = {"balanced", "implementation", "testing"}
PULL_SETUP_PRESETS = {"standard", "lean", "rich"}


def run_fixture_cycle(fixture_name: str) -> dict[str, Any]:
    """Load a fixture snapshot and run one minimal orchestration cycle."""
    fixture_root = Path(__file__).resolve().parent / "fixtures"
    store = JsonStore(fixture_root)
    snapshot = store.load_snapshot(fixture_name)
    snapshot = maybe_apply_fixture_project_config(fixture_root, fixture_name, snapshot)
    return run_cycle(snapshot)


def run_snapshot_cycle(
    snapshot_path: str | Path,
    *,
    project_config_path: str | Path | None = None,
    persistence_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run one orchestration cycle from an arbitrary snapshot file."""
    snapshot_path = Path(snapshot_path)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if project_config_path is not None:
        snapshot = apply_project_config(snapshot, load_project_config(project_config_path))
    persistence = build_local_workspace_persistence(persistence_root) if persistence_root else None
    return run_cycle(snapshot, persistence=persistence)


def _write_snapshot_file(path: str | Path, snapshot: dict[str, Any]) -> None:
    """Persist a snapshot JSON file in the standard pretty-printed format."""
    snapshot_path = Path(path)
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slugify(value: str, *, fallback: str) -> str:
    """Convert a directory or project name into a stable identifier."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _default_docs_for_root(root: Path) -> list[str]:
    """Return a small set of obvious docs paths when present."""
    candidates = [
        Path("README.md"),
        Path("docs"),
        Path("architecture"),
    ]
    return [str(path) for path in candidates if (root / path).exists()]


def _discover_workspace_projects(root: Path) -> list[dict[str, str]]:
    """Discover likely child projects directly under a workspace root."""
    projects: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        markers = [marker for marker in WORKSPACE_PROJECT_MARKERS if (child / marker).exists()]
        apple_markers = [path.name for path in child.glob("*.xcodeproj")] + [path.name for path in child.glob("*.xcworkspace")]
        marker_match = bool(markers)
        apple_project_match = bool(apple_markers)
        if not marker_match and not apple_project_match:
            continue
        slug = _slugify(child.name, fallback="project")
        projects.append(
            {
                "project_id": slug,
                "name": child.name,
                "repo_path": child.name,
                "markers": markers + apple_markers,
                "readme_excerpt": read_readme_excerpt(child),
            }
        )
    return projects


def _build_single_project_snapshot(root: Path, *, project_name: str | None = None) -> dict[str, Any]:
    """Build a starter snapshot for onboarding an existing repository."""
    derived_name = project_name or root.name or "Project"
    project_slug = _slugify(derived_name, fallback="project")
    initiative_id = f"{project_slug}-initiative"
    project_id = project_slug
    docs = _default_docs_for_root(root)

    return {
        "initiative": {
            "initiative_id": initiative_id,
            "name": derived_name,
            "goal": "Onboard an existing repository into DevForge orchestration.",
            "status": "active",
            "project_ids": [project_id],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": f"memory://initiative/{initiative_id}",
            "global_acceptance_goals": [
                "existing repository structure understood",
                "initial DevForge work plan defined",
            ],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": project_id,
                "initiative_id": initiative_id,
                "parent_project_id": None,
                "name": derived_name,
                "kind": "existing_repo",
                "status": "active",
                "current_phase": "analysis_design",
                "phases": [
                    "concept_collect",
                    "analysis_design",
                    "implementation",
                    "testing",
                    "acceptance",
                    "requirement_patch",
                ],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": [
                    "product_manager",
                    "execution_planner",
                    "technical_architect",
                    "software_engineer",
                    "qa_engineer",
                    "integration_owner",
                ],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": ["wp-repo-onboarding"],
                "seam_ids": [],
                "artifacts": {
                    "repo_paths": ["."],
                    "docs": docs,
                },
                "project_memory_ref": f"memory://project/{project_id}",
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [
            {
                "work_package_id": "wp-repo-onboarding",
                "initiative_id": initiative_id,
                "project_id": project_id,
                "phase": "analysis_design",
                "domain": "core",
                "role_id": "technical_architect",
                "title": "Existing repository onboarding",
                "goal": "Analyze the current repository, map its structure, and define the first DevForge work plan.",
                "status": "ready",
                "priority": 100,
                "executor": "codex",
                "fallback_executors": ["claude_code"],
                "inputs": [],
                "deliverables": [
                    "docs/devforge/repository-map.md",
                    "docs/devforge/initial-work-plan.md",
                ],
                "constraints": [
                    "work from the existing repository structure",
                    "avoid broad refactors before repository mapping is complete",
                ],
                "acceptance_criteria": [
                    "major code areas identified",
                    "initial work packages proposed",
                ],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
    }


def _build_workspace_snapshot(
    root: Path,
    *,
    project_name: str | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a workspace-aware snapshot using LLM business-project modeling."""
    derived_name = project_name or root.name or "Workspace"
    workspace_slug = _slugify(derived_name, fallback="workspace")
    initiative_id = f"{workspace_slug}-workspace"
    guardian_project_id = f"{workspace_slug}-guardian"
    discovered_projects_raw = _discover_workspace_projects(root)
    if not discovered_projects_raw:
        discovered_projects_raw = [
            {
                "project_id": f"{workspace_slug}-project",
                "name": "primary-project",
                "repo_path": ".",
                "markers": [],
                "readme_excerpt": read_readme_excerpt(root),
            }
        ]
    candidates = [WorkspaceCandidate(**item) for item in discovered_projects_raw]
    classifier = get_executor_adapter("topology_classifier")
    decision = classifier.classify_workspace(
        workspace_name=derived_name,
        candidates=candidates,
        llm_preferences=llm_preferences,
    )

    if decision.mode == "single_project":
        business_project_id = decision.business_project_id or _slugify(derived_name, fallback="project")
        docs = _default_docs_for_root(root)
        repo_paths = sorted({path for item in decision.surfaces for path in item.get("paths", [])}) or ["."]
        domains = [str(item.get("label") or item.get("surface_id") or "core") for item in decision.surfaces] or ["core"]
        return {
            "initiative": {
                "initiative_id": initiative_id,
                "name": decision.business_project_name,
                "goal": "Operate this repository as one business project with multiple implementation surfaces.",
                "status": "active",
                "project_ids": [business_project_id],
                "shared_concepts": [],
                "shared_contracts": [],
                "initiative_memory_ref": f"memory://initiative/{initiative_id}",
                "global_acceptance_goals": [
                    "business project map created",
                    "implementation surfaces identified",
                ],
                "requirement_event_ids": [],
                "scheduler_state": {},
            },
            "projects": [
                {
                    "project_id": business_project_id,
                    "initiative_id": initiative_id,
                    "parent_project_id": None,
                    "name": decision.business_project_name,
                    "kind": "business_project",
                    "status": "active",
                    "current_phase": "analysis_design",
                    "phases": [
                        "concept_collect",
                        "analysis_design",
                        "implementation",
                        "testing",
                        "acceptance",
                        "requirement_patch",
                    ],
                    "project_archetype": "general",
                    "domains": domains,
                    "active_roles": [
                        "product_manager",
                        "execution_planner",
                        "technical_architect",
                        "software_engineer",
                        "qa_engineer",
                        "integration_owner",
                    ],
                    "concept_model_refs": [],
                    "contracts": [],
                    "pull_policy_overrides": [],
                    "llm_preferences": {},
                    "knowledge_preferences": {},
                    "executor_policy_ref": None,
                    "work_package_ids": ["wp-business-project-onboarding"],
                    "seam_ids": [],
                    "artifacts": {
                        "repo_paths": repo_paths,
                        "docs": docs,
                    },
                    "project_memory_ref": f"memory://project/{business_project_id}",
                    "assumptions": [],
                    "requirement_events": [],
                    "children": [],
                    "coordination_project": False,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            "work_packages": [
                {
                    "work_package_id": "wp-business-project-onboarding",
                    "initiative_id": initiative_id,
                    "project_id": business_project_id,
                    "phase": "analysis_design",
                    "domain": domains[0],
                    "role_id": "technical_architect",
                    "title": "Business project onboarding",
                    "goal": "Analyze the business project, map implementation surfaces, and define the first cross-surface DevForge plan.",
                    "status": "ready",
                    "priority": 100,
                    "executor": "claude_code",
                    "fallback_executors": ["codex"],
                    "inputs": [],
                    "deliverables": [
                        "docs/devforge/business-project-map.md",
                        "docs/devforge/surface-seams.md",
                        "docs/devforge/initial-work-plan.md",
                    ],
                    "constraints": [
                        "model the repository around business intent",
                        "treat implementation directories as surfaces unless evidence suggests separate products",
                    ],
                    "acceptance_criteria": [
                        "implementation surfaces are identified",
                        "initial cross-surface work plan is proposed",
                    ],
                    "depends_on": [],
                    "blocks": [],
                    "related_seams": [],
                    "assumptions": [],
                    "artifacts_created": [],
                    "findings": [],
                    "handoff_notes": list(decision.reasoning),
                    "attempt_count": 0,
                    "max_attempts": 3,
                    "created_at": None,
                    "updated_at": None,
                }
            ],
            "executor_policies": [],
            "requirement_events": [],
            "seams": [],
            "workspace_modeling": dump_decision(decision),
        }

    discovered_projects = [
        {
            "project_id": str(item.get("project_id")),
            "name": str(item.get("label") or item.get("project_id")),
            "repo_path": str((item.get("paths") or ["."])[0]),
        }
        for item in decision.projects
    ] or [
        {
            "project_id": item.project_id,
            "name": item.name,
            "repo_path": item.repo_path,
        }
        for item in candidates
    ]
    project_ids = [guardian_project_id] + [item["project_id"] for item in discovered_projects]
    projects: list[dict[str, Any]] = [
        {
            "project_id": guardian_project_id,
            "initiative_id": initiative_id,
            "parent_project_id": None,
            "name": f"{derived_name} Guardian",
            "kind": "coordination",
            "status": "active",
            "current_phase": "analysis_design",
            "phases": [
                "concept_collect",
                "analysis_design",
                "implementation",
                "testing",
                "acceptance",
                "requirement_patch",
            ],
            "project_archetype": "workspace",
            "domains": ["coordination", "repo_governance"],
            "active_roles": [
                "product_manager",
                "execution_planner",
                "technical_architect",
                "integration_owner",
            ],
            "concept_model_refs": [],
            "contracts": [],
            "pull_policy_overrides": [],
            "llm_preferences": {},
            "knowledge_preferences": {},
            "executor_policy_ref": None,
            "work_package_ids": ["wp-workspace-guardian"],
            "seam_ids": [],
            "artifacts": {
                "repo_paths": ["."],
                "docs": _default_docs_for_root(root),
            },
            "project_memory_ref": f"memory://project/{guardian_project_id}",
            "assumptions": [],
            "requirement_events": [],
            "children": [item["project_id"] for item in discovered_projects],
            "coordination_project": True,
            "created_at": None,
            "updated_at": None,
        }
    ]

    for item in discovered_projects:
        child_root = root / item["repo_path"]
        projects.append(
            {
                "project_id": item["project_id"],
                "initiative_id": initiative_id,
                "parent_project_id": guardian_project_id,
                "name": item["name"],
                "kind": "existing_repo",
                "status": "active",
                "current_phase": "analysis_design",
                "phases": [
                    "concept_collect",
                    "analysis_design",
                    "implementation",
                    "testing",
                    "acceptance",
                    "requirement_patch",
                ],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": [
                    "technical_architect",
                    "software_engineer",
                    "qa_engineer",
                    "integration_owner",
                ],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": [],
                "seam_ids": [],
                "artifacts": {
                    "repo_paths": [item["repo_path"]],
                    "docs": [
                        str(Path(item["repo_path"]) / doc_path)
                        for doc_path in _default_docs_for_root(child_root)
                    ],
                },
                "project_memory_ref": f"memory://project/{item['project_id']}",
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        )

    return {
        "initiative": {
            "initiative_id": initiative_id,
            "name": derived_name,
            "goal": "Operate this workspace as a multi-project DevForge guardian entry.",
            "status": "active",
            "project_ids": project_ids,
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": f"memory://initiative/{initiative_id}",
            "global_acceptance_goals": [
                "workspace project map created",
                "cross-project governance entry established",
            ],
            "requirement_event_ids": [],
            "scheduler_state": {
                "foreground_project": guardian_project_id,
                "background_projects": [item["project_id"] for item in discovered_projects],
            },
        },
        "projects": projects,
        "work_packages": [
            {
                "work_package_id": "wp-workspace-guardian",
                "initiative_id": initiative_id,
                "project_id": guardian_project_id,
                "phase": "analysis_design",
                "domain": "coordination",
                "role_id": "integration_owner",
                "title": "Workspace guardian onboarding",
                "goal": "Analyze all discovered child projects, define shared seams, and produce the initial multi-project operating plan.",
                "status": "ready",
                "priority": 100,
                "executor": "claude_code",
                "fallback_executors": ["codex"],
                "inputs": [],
                "deliverables": [
                    "docs/devforge/workspace-map.md",
                    "docs/devforge/shared-seams.md",
                    "docs/devforge/initial-workspace-plan.md",
                ],
                "constraints": [
                    "preserve project boundaries",
                    "favor coordination and analysis before implementation",
                ],
                "acceptance_criteria": [
                    "all child projects are cataloged",
                    "shared seams and initial workstreams are identified",
                ],
                "depends_on": [],
                "blocks": [],
                "related_seams": [],
                "assumptions": [],
                "artifacts_created": [],
                "findings": [],
                "handoff_notes": [],
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
        "workspace_modeling": dump_decision(decision),
    }


def _build_init_project_config(project_id: str) -> dict[str, Any]:
    """Build a starter project config alongside the generated snapshot."""
    return _build_project_config_for_ids([project_id])


def _build_project_config_for_ids(
    project_ids: list[str],
    *,
    llm_preferences: dict[str, Any] | None = None,
    knowledge_preferences: dict[str, Any] | None = None,
    pull_policy_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build starter project config for one or more projects."""
    return {
        "projects": {
            project_id: {
                "llm_preferences": dict(llm_preferences or {}),
                "knowledge_preferences": {
                    "preferred_ids": list((knowledge_preferences or {}).get("preferred_ids", [])),
                    "excluded_ids": list((knowledge_preferences or {}).get("excluded_ids", [])),
                },
                "pull_policy_overrides": [dict(item) for item in (pull_policy_overrides or [])],
            }
            for project_id in project_ids
        }
    }


def _build_workspace_project_config(project_ids: list[str]) -> dict[str, Any]:
    """Build starter project config for all discovered workspace projects."""
    return _build_project_config_for_ids(project_ids)


def _resolve_llm_setup_preferences(root: Path, preset: str) -> dict[str, Any]:
    """Map a user-facing LLM setup preset to project config preferences."""
    if preset not in LLM_SETUP_PRESETS:
        raise ValueError(f"unsupported llm setup preset: {preset}")
    if preset == "offline":
        return {}
    if preset == "live":
        return default_live_llm_preferences(root)
    return load_llm_config(search_dir=root)


def _resolve_knowledge_setup_preferences(preset: str) -> dict[str, Any]:
    """Map a user-facing focus preset to knowledge preferences."""
    if preset not in KNOWLEDGE_SETUP_PRESETS:
        raise ValueError(f"unsupported knowledge setup preset: {preset}")
    if preset == "implementation":
        return {"preferred_ids": ["phase.implementation"], "excluded_ids": []}
    if preset == "testing":
        return {"preferred_ids": ["phase.testing"], "excluded_ids": []}
    return {"preferred_ids": [], "excluded_ids": []}


def _resolve_pull_setup_preferences(preset: str) -> list[dict[str, Any]]:
    """Map a user-facing context size preset to pull policy overrides."""
    if preset not in PULL_SETUP_PRESETS:
        raise ValueError(f"unsupported pull setup preset: {preset}")
    if preset == "lean":
        return [
            {"executor": "codex", "mode": "summary", "budget": 900},
            {"executor": "claude_code", "mode": "summary", "budget": 900},
        ]
    if preset == "rich":
        return [
            {"executor": "codex", "mode": "full", "budget": 4000},
            {"executor": "claude_code", "mode": "full", "budget": 4000},
        ]
    return []


def _prompt_choice(
    title: str,
    *,
    default: str,
    options: list[tuple[str, str]],
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> str:
    """Prompt for a simple numbered choice and return the selected key."""
    input_fn = input_fn or input
    output_fn = output_fn or print
    indexed = {str(index): key for index, (key, _label) in enumerate(options, start=1)}
    default_index = next(index for index, (key, _label) in enumerate(options, start=1) if key == default)
    output_fn(title)
    for index, (_key, label) in enumerate(options, start=1):
        marker = "default" if index == default_index else ""
        suffix = f" [{marker}]" if marker else ""
        output_fn(f"  {index}. {label}{suffix}")
    try:
        raw = input_fn(f"Choose 1-{len(options)} [{default_index}]: ").strip()
    except EOFError:
        return default
    except KeyboardInterrupt:
        output_fn("")
        return default
    if not raw:
        return default
    if raw in indexed:
        return indexed[raw]
    lowered = raw.lower()
    for key, _label in options:
        if lowered == key:
            return key
    return default


def _collect_guided_init_preferences(
    root: Path,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Collect user-facing setup choices and map them to project config fields."""
    input_fn = input_fn or input
    output_fn = output_fn or (lambda message: print(message, file=sys.stderr))
    output_fn("DevForge setup")
    output_fn("Choose how DevForge should run by default. Press Enter to keep the default.")
    llm_preset = _prompt_choice(
        "AI mode:",
        default="auto",
        options=[
            ("auto", "Auto: use llm.yaml when present, otherwise stay offline"),
            ("live", "Live AI: prefer live provider config for planning and routing"),
            ("offline", "Offline: avoid live model calls and use mock routing"),
        ],
        input_fn=input_fn,
        output_fn=output_fn,
    )
    knowledge_preset = _prompt_choice(
        "Default focus:",
        default="balanced",
        options=[
            ("balanced", "Balanced: let DevForge decide per phase"),
            ("implementation", "Implementation-heavy: bias toward build work"),
            ("testing", "Testing-heavy: bias toward verification work"),
        ],
        input_fn=input_fn,
        output_fn=output_fn,
    )
    pull_preset = _prompt_choice(
        "Context size:",
        default="standard",
        options=[
            ("standard", "Standard: use built-in pull policy defaults"),
            ("lean", "Lean: pull less context for faster, cheaper runs"),
            ("rich", "Rich: pull more context for deeper runs"),
        ],
        input_fn=input_fn,
        output_fn=output_fn,
    )
    return {
        "llm_preset": llm_preset,
        "knowledge_preset": knowledge_preset,
        "pull_preset": pull_preset,
        "llm_preferences": _resolve_llm_setup_preferences(root, llm_preset),
        "knowledge_preferences": _resolve_knowledge_setup_preferences(knowledge_preset),
        "pull_policy_overrides": _resolve_pull_setup_preferences(pull_preset),
    }


def initialize_project(
    root: str | Path = ".",
    *,
    force: bool = False,
    project_name: str | None = None,
    workspace_mode: bool = False,
    guided_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initialize DevForge scaffolding inside the local runtime directory."""
    root_path = Path(root).resolve()
    runtime_root = root_path / DEFAULT_RUNTIME_ROOT
    snapshot_path = runtime_root / DEFAULT_SNAPSHOT_FILENAME
    project_config_path = runtime_root / DEFAULT_PROJECT_CONFIG_FILENAME

    runtime_root.mkdir(parents=True, exist_ok=True)

    existing_paths = [path for path in (snapshot_path, project_config_path) if path.exists()]
    if existing_paths and not force:
        joined = ", ".join(str(path.relative_to(root_path)) for path in existing_paths)
        raise FileExistsError(f"refusing to overwrite existing files: {joined}")

    snapshot = (
        _build_workspace_snapshot(
            root_path,
            project_name=project_name,
            llm_preferences=default_live_llm_preferences(root_path),
        )
        if workspace_mode
        else _build_single_project_snapshot(root_path, project_name=project_name)
    )
    primary_project_id = snapshot["projects"][0]["project_id"]
    project_config = (
        _build_project_config_for_ids(
            [item["project_id"] for item in snapshot["projects"]]
            if workspace_mode and snapshot.get("workspace_modeling", {}).get("mode") == "workspace"
            else [primary_project_id],
            llm_preferences=guided_preferences.get("llm_preferences") if guided_preferences else None,
            knowledge_preferences=guided_preferences.get("knowledge_preferences") if guided_preferences else None,
            pull_policy_overrides=guided_preferences.get("pull_policy_overrides") if guided_preferences else None,
        )
        if workspace_mode
        else _build_project_config_for_ids(
            [primary_project_id],
            llm_preferences=guided_preferences.get("llm_preferences") if guided_preferences else None,
            knowledge_preferences=guided_preferences.get("knowledge_preferences") if guided_preferences else None,
            pull_policy_overrides=guided_preferences.get("pull_policy_overrides") if guided_preferences else None,
        )
    )

    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    project_config_path.write_text(json.dumps(project_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "runtime_root": str(runtime_root.relative_to(root_path)),
        "snapshot_path": str(snapshot_path.relative_to(root_path)),
        "project_config_path": str(project_config_path.relative_to(root_path)),
        "next_command": (
            f"devforge snapshot {snapshot_path.relative_to(root_path)} "
            f"--project-config {project_config_path.relative_to(root_path)} "
            f"--persistence-root {runtime_root.relative_to(root_path)}"
        ),
        "project_id": primary_project_id,
        "mode": snapshot.get("workspace_modeling", {}).get("mode", "workspace") if workspace_mode else "project",
        "discovered_projects": [item["project_id"] for item in _discover_workspace_projects(root_path)] if workspace_mode else [],
        "workspace_modeling": snapshot.get("workspace_modeling"),
        "setup_profile": {
            "llm": guided_preferences.get("llm_preset", "default") if guided_preferences else "default",
            "focus": guided_preferences.get("knowledge_preset", "balanced") if guided_preferences else "balanced",
            "context": guided_preferences.get("pull_preset", "standard") if guided_preferences else "standard",
        },
    }


def build_cli_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for local orchestration runs."""
    parser = argparse.ArgumentParser(prog="devforge", description="Run one DevForge orchestration cycle.")
    subparsers = parser.add_subparsers(dest="command", required=False)

    fixture_parser = subparsers.add_parser("fixture", help="Run a built-in fixture by name.")
    fixture_parser.add_argument("name", help="Fixture name without .json suffix, for example ecommerce_project.")
    fixture_parser.add_argument("--json", action="store_true", help="Print full JSON result instead of summary.")

    init_parser = subparsers.add_parser("init", help="Create starter DevForge files in ./.devforge/.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite generated files when they already exist.")
    init_parser.add_argument("--name", help="Optional project display name. Defaults to the current directory name.")
    init_parser.add_argument("--workspace", action="store_true", help="Initialize the current directory as a multi-project workspace guardian entry.")
    init_parser.add_argument("--guided", action="store_true", help="Always prompt for beginner-friendly setup choices.")
    init_parser.add_argument("--no-prompt", action="store_true", help="Skip interactive setup prompts and write plain defaults.")

    snapshot_parser = subparsers.add_parser("snapshot", help="Run a snapshot JSON file.")
    snapshot_parser.add_argument("path", help="Path to a snapshot JSON file.")
    snapshot_parser.add_argument("--project-config", help="Optional project config JSON applied before the cycle runs.")
    snapshot_parser.add_argument("--persistence-root", help="Optional local runtime root for sqlite/artifacts/memory.")
    snapshot_parser.add_argument("--json", action="store_true", help="Print full JSON result instead of summary.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    from devforge.repl import persist_session_bundle, run_interactive_session, _runs_from_cycle, _transitions_from_cycle
    from devforge.session import SessionState, ViewState

    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        return run_interactive_session(Path.cwd())
    if args.command == "fixture":
        result = run_fixture_cycle(args.name)
    elif args.command == "init":
        should_prompt = args.guided or (not args.no_prompt and sys.stdin.isatty() and sys.stdout.isatty())
        guided_preferences = _collect_guided_init_preferences(Path.cwd()) if should_prompt else None
        try:
            result = initialize_project(
                force=args.force,
                project_name=args.name,
                workspace_mode=args.workspace,
                guided_preferences=guided_preferences,
            )
        except FileExistsError as exc:
            parser.error(str(exc))
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    elif args.command == "snapshot":
        result = run_snapshot_cycle(
            args.path,
            project_config_path=args.project_config,
            persistence_root=args.persistence_root,
        )
        snapshot_path = Path(args.path).resolve()
        _write_snapshot_file(snapshot_path, result["snapshot"])
        root_path = snapshot_path.parent.parent if snapshot_path.name == DEFAULT_SNAPSHOT_FILENAME and snapshot_path.parent.name == DEFAULT_RUNTIME_ROOT else Path.cwd()
        runtime = result["runtime"]
        session = SessionState(
            session_id=f"session-{runtime.get('active_project_id', 'project')}",
            project_id=runtime.get("active_project_id", "project"),
            active_phase=runtime.get("current_phase"),
            active_feature=(result.get("selected_work_packages") or [None])[0],
            current_node_revision_ids=list(result.get("selected_work_packages", [])),
            recommended_next_action="Say '继续' when you want to resume from the latest cycle.",
            active_run_ids=[item.get("execution_id", "") for item in result.get("dispatches", [])],
            suspended_run_ids=[],
            last_state_transition_ids=[f"transition:{item.get('execution_id')}" for item in result.get("results", [])],
            mode="waiting_user",
        )
        persist_session_bundle(
            root_path,
            session=session,
            view=ViewState(),
            runs=_runs_from_cycle(result),
            transitions=_transitions_from_cycle(result),
            last_cycle=result,
        )
    else:
        parser.error(f"unsupported command: {args.command}")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        summary = {
            "cycle_id": result["runtime"]["cycle_id"],
            "active_project_id": result["runtime"]["active_project_id"],
            "selected_work_packages": result["selected_work_packages"],
            "dispatch_count": len(result["dispatches"]),
            "result_statuses": [item["status"] for item in result["results"]],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
