"""Integration test: concept → design → validate → expand → verify coverage."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    concept_collection_node,
    product_design_node,
    design_validation_node,
    closure_expansion_node,
)
from devforge.llm import MockLLMClient


def test_ecommerce_full_design_pipeline():
    """Simulate the full design pipeline for an ecommerce project."""
    llm = MockLLMClient()
    project = {
        "project_id": "P-ecom",
        "initiative_id": "I-001",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "concept_collect",
    }

    # Step 1: Concept collection
    state = RuntimeState(workspace_id="W-1", initiative_id="I-001", active_project_id="P-ecom")
    state = concept_collection_node(state, project=project, llm_client=llm)
    assert state.concept_decision is not None

    # Step 2: Product design
    state = product_design_node(state, project=project, llm_client=llm)
    assert state.product_design is not None
    assert len(state.product_design["domains"]) >= 4
    assert len(state.product_design["user_flows"]) >= 2
    assert len(state.product_design["interaction_matrix"]) >= 2

    # Step 3: Design validation
    state = design_validation_node(state)
    assert state.design_valid is True

    # Step 4: Closure expansion
    state = closure_expansion_node(state, max_ring=2)
    expansion = state.closure_expansion
    assert expansion is not None
    assert expansion["total_ring_0"] > 0
    assert expansion["total_ring_1"] > 0
    assert expansion["total_ring_2_plus"] <= expansion["total_ring_1"]
    assert expansion["coverage_ratio"] >= 0.8

    # Verify all Ring 0 tasks have closures
    ring_0_tasks = set(state.product_design["ring_0_tasks"])
    closure_sources = {c["source_task"] for c in expansion["closures"] if c["ring"] == 1}
    assert ring_0_tasks == closure_sources, f"Missing closure sources: {ring_0_tasks - closure_sources}"


def test_gaming_full_design_pipeline():
    """Simulate the full design pipeline for a gaming project."""
    llm = MockLLMClient()
    project = {
        "project_id": "P-game",
        "initiative_id": "I-002",
        "name": "Roguelike Dungeon",
        "project_archetype": "gaming",
        "current_phase": "concept_collect",
    }

    state = RuntimeState(workspace_id="W-2", initiative_id="I-002", active_project_id="P-game")
    state = concept_collection_node(state, project=project, llm_client=llm)
    state = product_design_node(state, project=project, llm_client=llm)
    state = design_validation_node(state)
    state = closure_expansion_node(state, max_ring=1)

    assert state.design_valid is True
    assert state.closure_expansion["total_ring_1"] > 0
    domain_names = {d["name"] for d in state.product_design["domains"]}
    assert "核心机制" in domain_names or "战斗" in domain_names


def test_invalid_design_triggers_replan():
    """Verify that a design with cycles triggers replan, not crash."""
    state = RuntimeState(workspace_id="W-3")
    state.product_design = {
        "design_id": "D-bad",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Bad Design",
        "problem_statement": "test",
        "target_users": ["user"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": ["B"]},
            {"domain_id": "B", "name": "B", "purpose": "b", "inputs": [], "outputs": [], "dependencies": ["A"]},
        ],
        "user_flows": [{"flow_id": "F-1", "name": "main", "role": "user", "steps": ["s1"]}],
        "ring_0_tasks": ["task1"],
        "interaction_matrix": [],
        "non_functional_requirements": [],
        "tech_choices": {},
        "closures": [],
        "unexplored_areas": [],
        "version": 1,
    }
    state = design_validation_node(state)
    assert state.design_valid is False
    assert state.replan_reason == "design_validation_failed"
