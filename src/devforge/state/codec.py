"""Helpers for converting between snapshot dicts and typed state objects."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .executor_policy import ExecutorPolicy
from .initiative import InitiativeState
from .project import ProjectArtifacts, ProjectState
from .requirement_event import RequirementEvent
from .seam import SeamChange, SeamRisk, SeamState
from .work_package import Assumption, Finding, WorkPackage


def _decode_assumptions(items: list[dict[str, Any]]) -> list[Assumption]:
    return [Assumption(**item) for item in items]


def _decode_findings(items: list[dict[str, Any]]) -> list[Finding]:
    return [Finding(**item) for item in items]


def decode_initiative(data: dict[str, Any]) -> InitiativeState:
    """Decode one initiative snapshot dict into a typed object."""
    return InitiativeState(**data)


def decode_project(data: dict[str, Any]) -> ProjectState:
    """Decode one project snapshot dict into a typed object."""
    project = dict(data)
    project["artifacts"] = ProjectArtifacts(**project.get("artifacts", {}))
    project["assumptions"] = _decode_assumptions(project.get("assumptions", []))
    return ProjectState(**project)


def decode_work_package(data: dict[str, Any]) -> WorkPackage:
    """Decode one work package snapshot dict into a typed object."""
    work_package = dict(data)
    work_package["assumptions"] = _decode_assumptions(work_package.get("assumptions", []))
    work_package["findings"] = _decode_findings(work_package.get("findings", []))
    return WorkPackage(**work_package)


def decode_seam(data: dict[str, Any]) -> SeamState:
    """Decode one seam snapshot dict into a typed object."""
    seam = dict(data)
    seam["risks"] = [SeamRisk(**item) for item in seam.get("risks", [])]
    seam["change_log"] = [SeamChange(**item) for item in seam.get("change_log", [])]
    return SeamState(**seam)


def decode_requirement_event(data: dict[str, Any]) -> RequirementEvent:
    """Decode one requirement event snapshot dict into a typed object."""
    return RequirementEvent(**data)


def decode_executor_policy(data: dict[str, Any]) -> ExecutorPolicy:
    """Decode one executor policy snapshot dict into a typed object."""
    return ExecutorPolicy(**data)


def encode_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert dataclasses inside a snapshot into plain dicts."""
    return asdict(snapshot) if hasattr(snapshot, "__dataclass_fields__") else {
        key: _encode_value(value) for key, value in snapshot.items()
    }


def _encode_value(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode_value(item) for key, item in value.items()}
    return value


def decode_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Decode a full snapshot into typed top-level sections."""
    return {
        "initiative": decode_initiative(snapshot["initiative"]) if "initiative" in snapshot else None,
        "projects": [decode_project(item) for item in snapshot.get("projects", [])],
        "work_packages": [decode_work_package(item) for item in snapshot.get("work_packages", [])],
        "seams": [decode_seam(item) for item in snapshot.get("seams", [])],
        "requirement_events": [decode_requirement_event(item) for item in snapshot.get("requirement_events", [])],
        "executor_policies": [decode_executor_policy(item) for item in snapshot.get("executor_policies", [])],
    }
