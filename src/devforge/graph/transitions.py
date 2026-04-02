"""Transition helpers for the meta-graph skeleton."""

from __future__ import annotations

from devforge.graph.runtime_state import RuntimeState


def next_step_for_state(state: RuntimeState) -> str:
    """Resolve the next coarse-grained meta step from runtime state."""
    if state.termination_signal:
        return "terminate"
    if state.needs_user_input:
        return "await_user"
    if state.pending_requirement_events:
        return "requirement_patch"
    if state.replan_reason:
        return "planning_and_shaping"
    if not state.current_workset:
        return "project_scheduler"
    if state.running_queue:
        return "batch_verification"
    return "batch_dispatch"

