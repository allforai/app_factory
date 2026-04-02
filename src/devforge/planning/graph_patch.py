"""Incremental graph patch operations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from devforge.state import RequirementEvent


def apply_patch_operations(snapshot: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a minimal set of graph patch operations to a snapshot dict."""
    result = deepcopy(snapshot)

    for op in operations:
        action = op["action"]
        target = op["target"]
        value = op.get("value")

        if action == "add":
            result.setdefault(target, []).append(value)
        elif action == "replace":
            result[target] = value
        elif action == "append_unique":
            result.setdefault(target, [])
            if value not in result[target]:
                result[target].append(value)
        elif action == "remove_by_id":
            item_id = op["id"]
            result[target] = [item for item in result.get(target, []) if item.get(op.get("id_field", "id")) != item_id]
        else:
            raise ValueError("Unsupported patch action: %s" % action)

    return result


def apply_requirement_events(snapshot: dict[str, Any], events: list[RequirementEvent]) -> dict[str, Any]:
    """Apply a minimal requirement-patch strategy to a snapshot."""
    result = deepcopy(snapshot)

    for event in events:
        if event.patch_status == "applied":
            continue

        if event.type in ("add", "remove", "modify"):
            for work_package in result.get("work_packages", []):
                if work_package["work_package_id"] in event.affected_work_packages:
                    work_package["status"] = "deprecated"

        patch_work_package = {
            "work_package_id": "requirement-patch-%s" % event.requirement_event_id,
            "initiative_id": event.initiative_id,
            "project_id": event.project_ids[0] if event.project_ids else "",
            "phase": "requirement_patch",
            "domain": event.affected_domains[0] if event.affected_domains else "planning",
            "role_id": "execution_planner",
            "title": "Requirement patch for %s" % event.requirement_event_id,
            "goal": event.summary,
            "status": "ready",
            "priority": 100,
            "executor": "python",
            "fallback_executors": ["claude_code"],
            "inputs": [],
            "deliverables": [],
            "constraints": [],
            "acceptance_criteria": ["patch reflected in planning graph"],
            "depends_on": [],
            "blocks": [],
            "related_seams": event.affected_seams,
            "assumptions": [],
            "artifacts_created": [],
            "findings": [],
            "handoff_notes": [],
            "attempt_count": 0,
            "max_attempts": 1,
            "created_at": event.created_at,
            "updated_at": event.applied_at,
        }

        result.setdefault("work_packages", []).append(patch_work_package)

        for raw_event in result.get("requirement_events", []):
            if raw_event["requirement_event_id"] == event.requirement_event_id:
                raw_event["patch_status"] = "applied"
                break

    return result


def apply_project_split(
    snapshot: dict[str, Any],
    *,
    source_project_id: str,
    child_projects: list[dict[str, Any]],
    seam: dict[str, Any],
    work_package_assignment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Split one project into child projects and auto-generate a seam."""
    result = deepcopy(snapshot)
    work_package_assignment = work_package_assignment or {}

    source_project = None
    for project in result.get("projects", []):
        if project["project_id"] == source_project_id:
            source_project = project
            break

    if source_project is None:
        raise ValueError("Unknown source project: %s" % source_project_id)

    source_project["status"] = "split_done"
    source_project["coordination_project"] = True
    source_project["children"] = [child["project_id"] for child in child_projects]
    source_project.setdefault("seam_ids", [])
    if seam["seam_id"] not in source_project["seam_ids"]:
        source_project["seam_ids"].append(seam["seam_id"])

    for child in child_projects:
        child.setdefault("seam_ids", [])
        if seam["seam_id"] not in child["seam_ids"]:
            child["seam_ids"].append(seam["seam_id"])
        result.setdefault("projects", []).append(child)

    result.setdefault("seams", []).append(seam)

    for work_package in result.get("work_packages", []):
        work_package_id = work_package["work_package_id"]
        if work_package_id in work_package_assignment:
            work_package["project_id"] = work_package_assignment[work_package_id]
            work_package.setdefault("related_seams", [])
            if seam["seam_id"] not in work_package["related_seams"]:
                work_package["related_seams"].append(seam["seam_id"])

    return result


def freeze_seam(snapshot: dict[str, Any], seam_id: str, *, version: str | None = None, summary: str = "seam frozen") -> dict[str, Any]:
    """Mark a seam as frozen and append a change-log entry."""
    result = deepcopy(snapshot)
    for seam in result.get("seams", []):
        if seam["seam_id"] == seam_id:
            seam["status"] = "frozen"
            seam.setdefault("change_log", []).append(
                {
                    "version": version or seam.get("contract_version", "v1"),
                    "summary": summary,
                }
            )
            return result
    raise ValueError("Unknown seam: %s" % seam_id)


def verify_seam(snapshot: dict[str, Any], seam_id: str, *, summary: str = "seam verified") -> dict[str, Any]:
    """Mark a seam as verified when it is already frozen or implemented."""
    result = deepcopy(snapshot)
    for seam in result.get("seams", []):
        if seam["seam_id"] == seam_id:
            if seam["status"] not in ("frozen", "implemented", "verified"):
                raise ValueError("Seam %s must be frozen or implemented before verification" % seam_id)
            seam["status"] = "verified"
            seam.setdefault("change_log", []).append(
                {
                    "version": seam.get("contract_version", "v1"),
                    "summary": summary,
                }
            )
            return result
    raise ValueError("Unknown seam: %s" % seam_id)
