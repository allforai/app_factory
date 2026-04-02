"""Minimal entrypoints for running orchestration cycles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from devforge.config import apply_project_config, load_project_config, maybe_apply_fixture_project_config
from devforge.graph.builder import run_cycle
from devforge.persistence import JsonStore, build_local_workspace_persistence


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


def build_cli_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for local orchestration runs."""
    parser = argparse.ArgumentParser(prog="devforge", description="Run one DevForge orchestration cycle.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture_parser = subparsers.add_parser("fixture", help="Run a built-in fixture by name.")
    fixture_parser.add_argument("name", help="Fixture name without .json suffix, for example ecommerce_project.")
    fixture_parser.add_argument("--json", action="store_true", help="Print full JSON result instead of summary.")

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
