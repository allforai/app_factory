"""Minimal LangGraph builder for the meta-graph skeleton."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from devforge.graph.nodes import concept_collection_node, graph_validation_node, planning_and_shaping_node, project_scheduler_node
from devforge.graph.runtime_state import RuntimeState
from devforge.planning import apply_requirement_events
from devforge.state import decode_snapshot


class RuntimeStateDict(TypedDict, total=False):
    """Dict state used by the minimal LangGraph builder."""

    workspace_id: str
    initiative_id: str | None
    active_project_id: str | None
    current_phase: str | None
    phase_goal: str | None
    foreground_project: str | None
    background_projects: list[str]
    ready_queue: list[str]
    running_queue: list[str]
    blocked_queue: list[str]
    pending_requirement_events: list[str]
    pending_seam_checks: list[str]
    current_workset: list[str]
    selected_knowledge: list[str]
    specialized_knowledge: dict[str, Any]
    node_knowledge_packet: dict[str, Any]
    concept_decision: dict[str, Any]
    planning_decision: dict[str, Any]
    recent_executor_results: list[str]
    snapshot: dict[str, Any] | None
    replan_reason: str | None
    needs_user_input: bool
    termination_signal: str | None


def _to_runtime(state: RuntimeStateDict) -> RuntimeState:
    return RuntimeState.from_dict(dict(state))


def _project_scheduler(state: RuntimeStateDict) -> RuntimeStateDict:
    return project_scheduler_node(_to_runtime(state)).to_dict()


def _project_for_runtime(snapshot: dict[str, Any] | None, runtime: RuntimeState) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    for project in snapshot.get("projects", []):
        if project["project_id"] == runtime.active_project_id:
            return project
    return None


def _requirement_patch(state: RuntimeStateDict) -> RuntimeStateDict:
    runtime = _to_runtime(state)
    if runtime.snapshot:
        typed = decode_snapshot(runtime.snapshot)
        pending_events = [
            event
            for event in typed["requirement_events"]
            if event.requirement_event_id in runtime.pending_requirement_events
        ]
        if pending_events:
            runtime.snapshot = apply_requirement_events(runtime.snapshot, pending_events)
    runtime.pending_requirement_events = []
    runtime.replan_reason = None
    return runtime.to_dict()


def _concept_collection(state: RuntimeStateDict) -> RuntimeStateDict:
    runtime = _to_runtime(state)
    return concept_collection_node(
        runtime,
        project=_project_for_runtime(runtime.snapshot, runtime),
        knowledge_ids=runtime.selected_knowledge,
        specialized_knowledge=runtime.specialized_knowledge,
    ).to_dict()


def _planning_and_shaping(state: RuntimeStateDict) -> RuntimeStateDict:
    runtime = _to_runtime(state)
    return planning_and_shaping_node(runtime, runtime.current_workset).to_dict()


def _graph_validation(state: RuntimeStateDict) -> RuntimeStateDict:
    return graph_validation_node(_to_runtime(state)).to_dict()


def _batch_dispatch(state: RuntimeStateDict) -> RuntimeStateDict:
    runtime = _to_runtime(state)
    runtime.running_queue = list(runtime.current_workset)
    return runtime.to_dict()


def _batch_verification(state: RuntimeStateDict) -> RuntimeStateDict:
    runtime = _to_runtime(state)
    runtime.recent_executor_results = ["verified:%s" % work_package_id for work_package_id in runtime.running_queue]
    runtime.running_queue = []
    return runtime.to_dict()


def _route_after_validation(state: RuntimeStateDict) -> str:
    runtime = _to_runtime(state)
    if runtime.replan_reason:
        return "project_scheduler"
    return "batch_dispatch"


def _route_after_scheduler(state: RuntimeStateDict) -> str:
    runtime = _to_runtime(state)
    if runtime.pending_requirement_events:
        return "requirement_patch"
    return "concept_collection"


def _route_after_dispatch(state: RuntimeStateDict) -> str:
    return "batch_verification"


def _route_after_verification(state: RuntimeStateDict) -> str:
    return END


def build_meta_graph() -> Any:
    """Build a minimal LangGraph StateGraph for the current meta-flow."""
    graph = StateGraph(RuntimeStateDict)
    graph.add_node("project_scheduler", _project_scheduler)
    graph.add_node("requirement_patch", _requirement_patch)
    graph.add_node("concept_collection", _concept_collection)
    graph.add_node("planning_and_shaping", _planning_and_shaping)
    graph.add_node("graph_validation", _graph_validation)
    graph.add_node("batch_dispatch", _batch_dispatch)
    graph.add_node("batch_verification", _batch_verification)

    graph.add_edge(START, "project_scheduler")
    graph.add_conditional_edges(
        "project_scheduler",
        _route_after_scheduler,
        {
            "requirement_patch": "requirement_patch",
            "concept_collection": "concept_collection",
        },
    )
    graph.add_edge("requirement_patch", "concept_collection")
    graph.add_edge("concept_collection", "planning_and_shaping")
    graph.add_edge("planning_and_shaping", "graph_validation")
    graph.add_conditional_edges(
        "graph_validation",
        _route_after_validation,
        {
            "project_scheduler": "project_scheduler",
            "batch_dispatch": "batch_dispatch",
        },
    )
    graph.add_conditional_edges(
        "batch_dispatch",
        _route_after_dispatch,
        {
            "batch_verification": "batch_verification",
        },
    )
    graph.add_conditional_edges(
        "batch_verification",
        _route_after_verification,
        {
            END: END,
        },
    )
    return graph.compile()
