"""Minimal entrypoints for running orchestration cycles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from devforge.config import apply_project_config, load_project_config, maybe_apply_fixture_project_config
from devforge.graph.builder import run_cycle
from devforge.persistence import JsonStore, build_local_workspace_persistence

DEFAULT_RUNTIME_ROOT = ".devforge-runtime"
DEFAULT_SNAPSHOT_FILENAME = "devforge.snapshot.json"
DEFAULT_PROJECT_CONFIG_FILENAME = "devforge.project_config.json"
WORKSPACE_PROJECT_MARKERS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    ".git",
)


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
    projects: list[dict[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not any((child / marker).exists() for marker in WORKSPACE_PROJECT_MARKERS):
            continue
        slug = _slugify(child.name, fallback="project")
        projects.append(
            {
                "project_id": slug,
                "name": child.name,
                "repo_path": child.name,
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
) -> dict[str, Any]:
    """Build a multi-project workspace snapshot with a guardian entry project."""
    derived_name = project_name or root.name or "Workspace"
    workspace_slug = _slugify(derived_name, fallback="workspace")
    initiative_id = f"{workspace_slug}-workspace"
    guardian_project_id = f"{workspace_slug}-guardian"
    discovered_projects = _discover_workspace_projects(root)
    if not discovered_projects:
        discovered_projects = [
            {
                "project_id": f"{workspace_slug}-project",
                "name": "primary-project",
                "repo_path": ".",
            }
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
    }


def _build_init_project_config(project_id: str) -> dict[str, Any]:
    """Build a starter project config alongside the generated snapshot."""
    return {
        "projects": {
            project_id: {
                "llm_preferences": {},
                "knowledge_preferences": {
                    "preferred_ids": [],
                    "excluded_ids": [],
                },
                "pull_policy_overrides": [],
            }
        }
    }


def initialize_project(
    root: str | Path = ".",
    *,
    force: bool = False,
    project_name: str | None = None,
    workspace_mode: bool = False,
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
        _build_workspace_snapshot(root_path, project_name=project_name)
        if workspace_mode
        else _build_single_project_snapshot(root_path, project_name=project_name)
    )
    primary_project_id = snapshot["projects"][0]["project_id"]
    project_config = _build_init_project_config(primary_project_id)

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
        "mode": "workspace" if workspace_mode else "project",
        "discovered_projects": [item["project_id"] for item in snapshot["projects"][1:]] if workspace_mode else [],
    }


def build_cli_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for local orchestration runs."""
    parser = argparse.ArgumentParser(prog="devforge", description="Run one DevForge orchestration cycle.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture_parser = subparsers.add_parser("fixture", help="Run a built-in fixture by name.")
    fixture_parser.add_argument("name", help="Fixture name without .json suffix, for example ecommerce_project.")
    fixture_parser.add_argument("--json", action="store_true", help="Print full JSON result instead of summary.")

    init_parser = subparsers.add_parser("init", help="Create starter DevForge files in ./.devforge-runtime/.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite generated files when they already exist.")
    init_parser.add_argument("--name", help="Optional project display name. Defaults to the current directory name.")
    init_parser.add_argument("--workspace", action="store_true", help="Initialize the current directory as a multi-project workspace guardian entry.")

    snapshot_parser = subparsers.add_parser("snapshot", help="Run a snapshot JSON file.")
    snapshot_parser.add_argument("path", help="Path to a snapshot JSON file.")
    snapshot_parser.add_argument("--project-config", help="Optional project config JSON applied before the cycle runs.")
    snapshot_parser.add_argument("--persistence-root", help="Optional local runtime root for sqlite/artifacts/memory.")
    snapshot_parser.add_argument("--json", action="store_true", help="Print full JSON result instead of summary.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if args.command == "fixture":
        result = run_fixture_cycle(args.name)
    elif args.command == "init":
        try:
            result = initialize_project(force=args.force, project_name=args.name, workspace_mode=args.workspace)
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
