"""Minimal meta-graph node functions."""

from __future__ import annotations

from dataclasses import asdict

from devforge.llm import LLMClient
from devforge.graph.runtime_state import RuntimeState
from devforge.planning import llm_concept_collection_decider, llm_planning_decider
from devforge.planning.design_generator import generate_product_design
from devforge.planning.design_validator import validate_design
from devforge.planning.closure_expander import expand_closures
from devforge.planning.acceptance import evaluate_acceptance
from devforge.planning.gap_analyzer import analyze_gaps
from devforge.state.design import DomainSpec, ProductDesign, UserFlow


def project_scheduler_node(state: RuntimeState) -> RuntimeState:
    """Move the foreground project into the active slot when needed."""
    if state.foreground_project and not state.active_project_id:
        state.active_project_id = state.foreground_project
    return state


def concept_collection_node(
    state: RuntimeState,
    *,
    project: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    specialized_knowledge: dict[str, object] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Attach a concept collection decision to the runtime state."""
    selected_knowledge = knowledge_ids or []
    specialized = specialized_knowledge or {}
    decision = llm_concept_collection_decider(
        project=project or {},
        selected_knowledge=selected_knowledge,
        specialized_knowledge=specialized,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )
    state.selected_knowledge = selected_knowledge
    state.specialized_knowledge = specialized
    state.concept_decision = asdict(decision)
    state.current_phase = decision.phase or state.current_phase
    state.phase_goal = decision.goal or state.phase_goal
    return state


def planning_and_shaping_node(
    state: RuntimeState,
    workset_ids: list[str],
    *,
    project: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    specialized_knowledge: dict[str, object] | None = None,
    node_knowledge_packet: dict[str, object] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Attach a newly planned workset to the runtime state."""
    selected_knowledge = knowledge_ids or []
    specialized = specialized_knowledge or {}
    packet = node_knowledge_packet or {}
    decision = llm_planning_decider(
        project=project or {},
        workset_ids=workset_ids,
        selected_knowledge=selected_knowledge,
        specialized_knowledge=specialized,
        node_knowledge_packet=packet,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )
    state.current_workset = decision.selected_workset
    state.selected_knowledge = selected_knowledge
    state.specialized_knowledge = specialized
    state.node_knowledge_packet = packet
    state.planning_decision = asdict(decision)
    state.current_phase = decision.phase or state.current_phase
    state.phase_goal = decision.goal or state.phase_goal
    state.replan_reason = None
    return state


def graph_validation_node(state: RuntimeState) -> RuntimeState:
    """Set a replan reason when the current workset is empty."""
    if not state.current_workset:
        state.replan_reason = "no_runnable_work"
    return state


def product_design_node(
    state: RuntimeState,
    *,
    project: dict[str, object] | None = None,
    concept: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Generate a product design and attach it to the runtime state."""
    effective_concept = concept or state.concept_decision or {}
    effective_knowledge = knowledge_ids or state.selected_knowledge or []
    design = generate_product_design(
        concept=effective_concept,
        project=project or {},
        knowledge_ids=effective_knowledge,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )
    state.product_design = asdict(design)
    return state


def design_validation_node(state: RuntimeState) -> RuntimeState:
    """Validate the product design and record results in runtime state."""
    if state.product_design is None:
        state.design_valid = False
        state.replan_reason = "no_design"
        return state

    pd = state.product_design
    domains = [
        DomainSpec(
            domain_id=d["domain_id"],
            name=d["name"],
            purpose=d["purpose"],
            inputs=list(d.get("inputs", [])),
            outputs=list(d.get("outputs", [])),
            dependencies=list(d.get("dependencies", [])),
        )
        for d in pd.get("domains", [])
    ]
    user_flows = [
        UserFlow(
            flow_id=f["flow_id"],
            name=f["name"],
            role=f["role"],
            steps=list(f.get("steps", [])),
            entry_point=f.get("entry_point", ""),
            exit_point=f.get("exit_point", ""),
        )
        for f in pd.get("user_flows", [])
    ]
    design = ProductDesign(
        design_id=pd.get("design_id", ""),
        initiative_id=pd.get("initiative_id", ""),
        project_id=pd.get("project_id", ""),
        product_name=pd.get("product_name", ""),
        problem_statement=pd.get("problem_statement", ""),
        target_users=list(pd.get("target_users", [])),
        domains=domains,
        user_flows=user_flows,
        ring_0_tasks=list(pd.get("ring_0_tasks", [])),
    )

    previous_issue_types = [
        issue["error_type"]
        for issue in state.design_validation_issues
        if isinstance(issue, dict) and "error_type" in issue
    ]
    result = validate_design(design, previous_issues=previous_issue_types)

    state.design_valid = result.valid
    state.design_validation_issues = [
        {"error_type": e.error_type, "message": e.message, "domain_ids": e.domain_ids}
        for e in result.errors
    ]
    if not result.valid:
        state.replan_reason = "design_validation_failed"
    return state


def closure_expansion_node(
    state: RuntimeState,
    *,
    concept_boundary: list[str] | None = None,
    max_ring: int = 1,
) -> RuntimeState:
    """Expand ring-0 tasks into closures and attach results to runtime state."""
    pd = state.product_design or {}
    ring_0_tasks = list(pd.get("ring_0_tasks", []))
    boundary = concept_boundary if concept_boundary is not None else ring_0_tasks
    result = expand_closures(
        ring_0_tasks=ring_0_tasks,
        concept_boundary=boundary,
        max_ring=max_ring,
    )
    state.closure_expansion = {
        "total_ring_0": result.total_ring_0,
        "total_ring_1": result.total_ring_1,
        "total_ring_2_plus": result.total_ring_2_plus,
        "coverage_ratio": result.coverage_ratio,
        "stopped_reason": result.stopped_reason,
        "closures": [asdict(c) for c in result.closures],
    }
    return state


def acceptance_and_gap_check_node(
    state: RuntimeState,
    *,
    acceptance_goals: list[str] | None = None,
    work_package_results: list[dict[str, object]] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Evaluate deliverables against acceptance goals. Set termination or replan."""
    verdict = evaluate_acceptance(
        project_id=state.active_project_id or "",
        cycle_id=state.cycle_id or "",
        acceptance_goals=acceptance_goals or [],
        work_package_results=work_package_results or [],
        design_summary=state.product_design or {},
        closure_expansion=state.closure_expansion or {},
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )
    state.acceptance_verdict = {
        "verdict_id": verdict.verdict_id,
        "project_id": verdict.project_id,
        "is_production_ready": verdict.is_production_ready,
        "overall_score": verdict.overall_score,
        "summary": verdict.summary,
        "goal_checks": [{"goal": gc.goal, "status": gc.status, "reason": gc.reason} for gc in verdict.goal_checks],
        "gaps": [{"gap_id": g.gap_id, "description": g.description, "severity": g.severity, "attributed_domain": g.attributed_domain, "remediation_target": g.remediation_target} for g in verdict.gaps],
        "closure_density": {"total_ring_0": verdict.closure_density.total_ring_0, "covered": verdict.closure_density.covered, "coverage_ratio": verdict.closure_density.coverage_ratio} if verdict.closure_density else None,
        "role_evaluations": verdict.role_evaluations,
    }
    if verdict.is_production_ready:
        state.termination_signal = True
    else:
        gap_result = analyze_gaps(verdict)
        state.replan_reason = f"acceptance_gaps:{gap_result.reentry_point}" if gap_result.reentry_point else "acceptance_failed"
    return state
