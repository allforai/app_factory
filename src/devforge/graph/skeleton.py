"""Meta-graph node names and coarse transition hints."""

from __future__ import annotations

META_GRAPH_NODES = (
    "project_scheduler",
    "context_analysis",
    "concept_collection",
    "planning_and_shaping",
    "graph_validation",
    "batch_dispatch",
    "batch_verification",
    "acceptance_and_gap_check",
    "requirement_patch",
)

NEXT_STEP_BY_EVENT = {
    "needs_concept": "concept_collection",
    "concept_ready": "planning_and_shaping",
    "plan_invalid": "planning_and_shaping",
    "plan_valid": "batch_dispatch",
    "batch_done": "batch_verification",
    "needs_patch": "requirement_patch",
    "continue": "project_scheduler",
    "patched": "planning_and_shaping",
}

