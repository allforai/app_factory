"""Tests for design-related graph nodes."""

from app_factory.graph.runtime_state import RuntimeState
from app_factory.graph.nodes import product_design_node, design_validation_node, closure_expansion_node
from app_factory.llm import MockLLMClient


def test_product_design_node_attaches_design():
    state = RuntimeState(workspace_id="W-1", initiative_id="I-1", active_project_id="P-1")
    project = {
        "project_id": "P-1",
        "initiative_id": "I-1",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "analysis_design",
    }
    concept = {
        "goal": "collect concept for marketplace",
        "focus_areas": ["交易流程"],
    }
    updated = product_design_node(state, project=project, concept=concept, llm_client=MockLLMClient())
    assert updated.product_design is not None
    assert updated.product_design["project_id"] == "P-1"
    assert len(updated.product_design["domains"]) > 0


def test_design_validation_node_valid():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "design_id": "D-1",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Test",
        "problem_statement": "test",
        "target_users": ["user"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": []},
        ],
        "user_flows": [
            {"flow_id": "F-1", "name": "main", "role": "user", "steps": ["s1"]},
        ],
        "ring_0_tasks": ["task1"],
        "interaction_matrix": [],
        "non_functional_requirements": [],
        "tech_choices": {},
        "closures": [],
        "unexplored_areas": [],
        "version": 1,
    }
    updated = design_validation_node(state)
    assert updated.design_valid is True
    assert updated.replan_reason is None


def test_design_validation_node_invalid_triggers_replan():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "design_id": "D-1",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Test",
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
    updated = design_validation_node(state)
    assert updated.design_valid is False
    assert updated.replan_reason == "design_validation_failed"


def test_closure_expansion_node():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "ring_0_tasks": ["认证", "下单"],
    }
    updated = closure_expansion_node(state, concept_boundary=["认证", "下单"])
    assert updated.closure_expansion is not None
    assert updated.closure_expansion["total_ring_0"] == 2
    assert updated.closure_expansion["total_ring_1"] > 0
