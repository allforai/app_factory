"""Local deterministic executor helpers for non-network fallback work."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _write_acceptance_report(request: dict[str, Any], working_dir: Path) -> dict[str, Any]:
    payload = request.get("payload", {})
    notes = list(payload.get("handoff_notes", []))
    previous_attempts = payload.get("previous_attempts", {})
    notes.extend(previous_attempts.get("handoff_notes", []))
    checks = list(payload.get("checks", []))
    deliverables = list(request.get("deliverables", []))
    report_relpath = deliverables[0] if deliverables else "docs/devforge/self-hosting-acceptance.md"
    report_path = working_dir / report_relpath
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = "\n".join(
        [
            f"# {request.get('work_package_id', 'Acceptance').replace('-', ' ').title()}",
            "",
            f"Cycle: {request.get('cycle_id') or 'unknown'}",
            f"Work package: {request.get('work_package_id') or 'unknown'}",
            "",
            "## Verdict",
            "DevForge orchestration reached a stable decision point, but external executor readiness is still blocking full autonomous completion.",
            "",
            "## Acceptance Checks",
            *[f"- {check}" for check in checks],
            "",
            "## Blocking Evidence",
            *([f"- {note}" for note in notes] or ["- No executor evidence was captured."]),
            "",
            "## Next Actions",
            "- Restore network reachability for the Codex CLI subprocess path.",
            "- Log in to Claude Code before retrying the fallback executor path.",
            "- Re-run the self-hosting regression cycle after executor readiness is restored.",
            "",
        ]
    )
    report_path.write_text(report, encoding="utf-8")
    return {
        "summary": "local acceptance report generated from executor evidence",
        "artifacts_created": [report_relpath],
        "handoff_notes": [
            "local acceptance fallback captured executor readiness blockers",
        ],
    }


def run_local_request(request: dict[str, Any], *, working_dir: str | None = None) -> dict[str, Any]:
    payload = request.get("payload", {})
    work_package_id = request.get("work_package_id", "")
    cycle_id = request.get("cycle_id")
    root = Path(working_dir or request.get("working_dir") or ".").resolve()
    result = {
        "execution_id": f"python:{work_package_id}",
        "work_package_id": work_package_id,
        "cycle_id": cycle_id,
        "status": "completed",
        "summary": "local python executor completed",
        "artifacts_created": [],
        "artifacts_modified": [],
        "tests_run": [],
        "findings": [],
        "handoff_notes": [],
        "raw_output_ref": None,
    }
    if payload.get("style") == "local_acceptance":
        result.update(_write_acceptance_report(request, root))
    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        raise SystemExit("missing request payload")
    request = json.loads(argv[0])
    print(json.dumps(run_local_request(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
