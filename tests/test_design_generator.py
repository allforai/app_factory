"""Tests for LLM-driven product design generator."""

from __future__ import annotations

from devforge.planning.design_generator import generate_product_design


_ECOMMERCE_PROJECT = {
    "name": "二手交易平台",
    "project_archetype": "ecommerce",
    "current_phase": "design",
}

_ECOMMERCE_CONCEPT = {
    "problem_statement": "年轻人需要一个有社区感的二手交易平台",
    "target_users": ["buyer", "seller", "admin"],
}

_GAMING_PROJECT = {
    "name": "Battle Arena",
    "project_archetype": "gaming",
    "current_phase": "design",
}

_GAMING_CONCEPT = {
    "problem_statement": "玩家需要一款快节奏的竞技游戏",
    "target_users": ["player"],
}


def test_generate_design_from_concept() -> None:
    """Ecommerce project produces a design with domains, user_flows, interaction_matrix, ring_0_tasks."""
    design = generate_product_design(
        concept=_ECOMMERCE_CONCEPT,
        project=_ECOMMERCE_PROJECT,
    )

    assert design.product_name
    assert len(design.domains) >= 1
    assert len(design.user_flows) >= 1
    assert len(design.interaction_matrix) >= 1
    assert len(design.ring_0_tasks) >= 1

    # Verify domain objects have expected fields
    domain = design.domains[0]
    assert domain.domain_id
    assert domain.name
    assert domain.purpose

    # Verify user flow objects
    flow = design.user_flows[0]
    assert flow.flow_id
    assert flow.name
    assert flow.role

    # Verify interaction matrix entries
    entry = design.interaction_matrix[0]
    assert entry.feature
    assert entry.role
    assert entry.frequency in ("high", "low")
    assert entry.user_volume in ("high", "low")


def test_generate_design_includes_non_functional() -> None:
    """Gaming project produces non_functional_requirements."""
    design = generate_product_design(
        concept=_GAMING_CONCEPT,
        project=_GAMING_PROJECT,
    )

    assert len(design.non_functional_requirements) >= 1
    for req in design.non_functional_requirements:
        assert isinstance(req, str)
        assert req.strip()


def test_design_has_interaction_matrix_for_all_quadrants() -> None:
    """Ecommerce project has >= 2 quadrants in interaction matrix."""
    design = generate_product_design(
        concept=_ECOMMERCE_CONCEPT,
        project=_ECOMMERCE_PROJECT,
    )

    quadrants: set[tuple[str, str]] = set()
    for entry in design.interaction_matrix:
        quadrants.add((entry.frequency, entry.user_volume))

    assert len(quadrants) >= 2, (
        f"Expected at least 2 distinct (frequency, user_volume) quadrants, got: {quadrants}"
    )
