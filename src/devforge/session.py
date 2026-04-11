"""Session-level interaction protocol models for the DevForge CLI/TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SessionMode = Literal[
    "idle",
    "planning",
    "executing",
    "waiting_user",
    "attached",
]

RunStatus = Literal[
    "queued",
    "running",
    "suspended",
    "completed",
    "failed",
    "cancelled",
]

ViewFocus = Literal[
    "main",
    "runs",
    "state",
    "attached",
]

IntentKind = Literal[
    "continue_cycle",
    "show_status",
    "list_runs",
    "observe_run",
    "attach_run",
    "detach_run",
    "interrupt_run",
    "apply_run_result",
    "merge_run_results",
    "input_information",
    "list_work_packages",
    "quit_session",
    # workflow engine
    "show_workflow",
    "run_workflow",
    "init_workflow",
    "confirm_workflow",
    "log_workflow",
    "reset_workflow_node",
    "list_workflows",
    "switch_workflow",
]

TransitionObjectType = Literal[
    "node",
    "run",
    "session",
]


@dataclass(slots=True)
class SessionState:
    """Top-level state for one interactive DevForge session."""

    session_id: str
    project_id: str
    active_phase: str | None = None
    active_feature: str | None = None
    current_node_revision_ids: list[str] = field(default_factory=list)
    recommended_next_action: str | None = None
    active_run_ids: list[str] = field(default_factory=list)
    suspended_run_ids: list[str] = field(default_factory=list)
    last_state_transition_ids: list[str] = field(default_factory=list)
    mode: SessionMode = "idle"


@dataclass(slots=True)
class RunRecord:
    """One executor run visible to the interactive session."""

    run_id: str
    executor: str
    title: str
    status: RunStatus
    trigger_ref: str | None = None
    related_node_ids: list[str] = field(default_factory=list)
    summary: str = ""
    latest_output: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class ViewState:
    """Current terminal view/focus for the session UI."""

    focus: ViewFocus = "main"
    attached_run_id: str | None = None
    selected_run_id: str | None = None
    show_state_timeline: bool = True
    show_executor_board: bool = True


@dataclass(slots=True)
class UserIntent:
    """Normalized intent parsed from natural language or slash commands."""

    kind: IntentKind
    target_run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TransitionLogEntry:
    """One visible transition entry for state/run/session changes."""

    transition_id: str
    object_type: TransitionObjectType
    object_id: str
    before: str
    after: str
    reason: str
    created_at: str | None = None
