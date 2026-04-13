"""TypedDict definitions for the DevForge workflow engine."""

from __future__ import annotations

from typing import Literal, TypedDict, NotRequired

NodeStatus = Literal["pending", "running", "completed", "failed", "needs_refactor"]

# Engine-internal phase (stored in manifest.workflow_status)
WorkflowPhase = Literal["planning", "awaiting_confirm", "running", "complete", "failed"]

# User-visible lifecycle status (stored in index.json per workflow)
WorkflowStatus = Literal["active", "complete", "paused", "failed"]

NodeMode = Literal["planning", "discovery"]

TransitionStatus = Literal["completed", "failed", "needs_refactor"]
NodeStrategy = Literal["REVERSE_ANALYSIS", "FULL_STACK_VALIDATION", "TDD_REFACTOR", "GOVERNANCE"]


class NodeManifestEntry(TypedDict):
    id: str
    status: NodeStatus
    strategy: NodeStrategy | None
    depends_on: list[str]
    exit_artifacts: list[str]
    executor: str
    mode: NodeMode | None     # None = regular node, "planning" = planner node
    parent_node_id: str | None
    depth: int
    attempt_count: int        # cumulative execution attempts
    last_started_at: str | None
    last_completed_at: str | None
    last_error: str | None
    pid: int | None
    log_path: str | None


class NodeDefinition(TypedDict):
    id: str
    capability: str
    strategy: NodeStrategy | None
    goal: str
    exit_artifacts: list[str]
    knowledge_refs: list[str]
    executor: str
    mode: NodeMode | None     # None | "planning"
    depends_on: list[str]     # list of node ids this node depends on
    attention_weight: NotRequired[float]


class WorkflowManifest(TypedDict):
    id: str
    goal: str
    created_at: str
    workflow_status: WorkflowPhase   # engine-internal phase
    nodes: list[NodeManifestEntry]


class WorkflowIndexEntry(TypedDict):
    id: str
    goal: str
    status: WorkflowStatus
    created_at: str


class WorkflowIndex(TypedDict):
    schema_version: str
    active_workflow_id: str | None
    workflows: list[WorkflowIndexEntry]


class TransitionEntry(TypedDict):
    node: str
    status: TransitionStatus
    started_at: str
    completed_at: str
    artifacts_created: list[str]
    error: str | None


class PullContextEvent(TypedDict):
    event_id: str
    node_id: str
    path: str
    kind: str
    bytes_read: int
    created_at: str


class PlannerOutput(TypedDict):
    nodes: list[NodeDefinition]
    summary: str
