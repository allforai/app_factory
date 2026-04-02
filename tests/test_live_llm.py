"""Live LLM integration tests — requires GEMINI_API_KEY.

Run with: uv run python -m pytest tests/test_live_llm.py -v -s
Skip if no key: tests auto-skip when GEMINI_API_KEY is not set.
"""

from __future__ import annotations

import os

import pytest

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    concept_collection_node,
    product_design_node,
    design_validation_node,
    closure_expansion_node,
    acceptance_and_gap_check_node,
)
from devforge.llm.factory import build_llm_client

GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
skip_no_key = pytest.mark.skipif(not GEMINI_KEY, reason="GEMINI_API_KEY not set")


def _make_live_client():
    return build_llm_client("google", model="gemini-2.5-flash", api_key=GEMINI_KEY)


@skip_no_key
def test_live_concept_collection():
    """Real LLM: concept collection for ecommerce project."""
    llm = _make_live_client()
    project = {
        "project_id": "P-live",
        "initiative_id": "I-live",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "concept_collect",
    }
    state = RuntimeState(workspace_id="W-live", initiative_id="I-live", active_project_id="P-live")
    state = concept_collection_node(state, project=project, llm_client=llm)

    print(f"\n=== Concept Decision ===")
    print(f"Phase: {state.concept_decision.get('phase')}")
    print(f"Goal: {state.concept_decision.get('goal')}")
    print(f"Focus: {state.concept_decision.get('focus_areas')}")
    print(f"Questions: {state.concept_decision.get('questions')}")

    assert state.concept_decision is not None
    assert state.concept_decision.get("goal")


@skip_no_key
def test_live_product_design():
    """Real LLM: generate product design for ecommerce."""
    llm = _make_live_client()
    project = {
        "project_id": "P-live",
        "initiative_id": "I-live",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "analysis_design",
    }
    concept = {
        "goal": "面向年轻人的二手交易平台，支持发布商品、搜索、下单、支付、评价，有社区感",
        "focus_areas": ["用户交易流程", "社区互动", "信任体系", "管理后台"],
    }
    state = RuntimeState(workspace_id="W-live", initiative_id="I-live", active_project_id="P-live")
    state = product_design_node(state, project=project, concept=concept, llm_client=llm)

    design = state.product_design
    print(f"\n=== Product Design ===")
    print(f"Product: {design.get('product_name')}")
    print(f"Domains: {[d.get('name') for d in design.get('domains', [])]}")
    print(f"User Flows: {[f.get('name') for f in design.get('user_flows', [])]}")
    print(f"Ring 0 Tasks: {design.get('ring_0_tasks')}")
    print(f"Interaction Matrix: {len(design.get('interaction_matrix', []))} entries")
    print(f"NFRs: {design.get('non_functional_requirements')}")

    assert design is not None
    assert len(design.get("domains", [])) > 0, "LLM should produce at least 1 domain"
    assert len(design.get("ring_0_tasks", [])) > 0, "LLM should produce Ring 0 tasks"


@skip_no_key
def test_live_full_pipeline():
    """Real LLM: concept → design → validate → expand → accept."""
    llm = _make_live_client()
    project = {
        "project_id": "P-live",
        "initiative_id": "I-live",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "concept_collect",
    }

    state = RuntimeState(workspace_id="W-live", initiative_id="I-live", active_project_id="P-live")

    # 1. Concept
    state = concept_collection_node(state, project=project, llm_client=llm)
    print(f"\n[1] Concept: {state.concept_decision.get('goal')}")

    # 2. Design
    state = product_design_node(state, project=project, llm_client=llm)
    design = state.product_design
    print(f"[2] Design: {len(design.get('domains', []))} domains, {len(design.get('user_flows', []))} flows")

    # 3. Validate
    state = design_validation_node(state)
    print(f"[3] Valid: {state.design_valid}")
    if not state.design_valid:
        print(f"    Issues: {state.design_validation_issues}")

    # 4. Closure expansion
    ring_0 = design.get("ring_0_tasks", [])
    if ring_0:
        state = closure_expansion_node(state, max_ring=2)
        exp = state.closure_expansion
        print(f"[4] Closures: ring0={exp['total_ring_0']}, ring1={exp['total_ring_1']}, coverage={exp['coverage_ratio']:.0%}")
    else:
        print("[4] Skipped (no ring_0_tasks)")

    # 5. Acceptance
    all_results = [
        {"work_package_id": f"WP-{i}", "status": "completed", "summary": f"task {i} completed"}
        for i in range(len(ring_0))
    ]
    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["购买流程端到端可用", "管理后台可审核", "社区感体现"],
        work_package_results=all_results,
        llm_client=llm,
    )
    verdict = state.acceptance_verdict
    print(f"[5] Verdict: ready={verdict['is_production_ready']}, score={verdict['overall_score']}")
    print(f"    Summary: {verdict['summary']}")
    if verdict.get("gaps"):
        print(f"    Gaps: {[g['description'] for g in verdict['gaps']]}")

    assert verdict is not None
    assert "is_production_ready" in verdict
