"""Tests for Ring-based closure expansion with convergence control."""

from devforge.planning.closure_expander import (
    expand_closures,
    ClosureExpansionResult,
    CLOSURE_DIMENSIONS,
)
from devforge.state.design import ClosureItem


def test_ring_1_expansion_from_core_tasks():
    ring_0_tasks = ["认证", "下单", "支付"]
    result = expand_closures(ring_0_tasks=ring_0_tasks, concept_boundary=ring_0_tasks, max_ring=1)
    assert isinstance(result, ClosureExpansionResult)
    assert len(result.closures) > 0
    assert all(c.ring == 1 for c in result.closures)
    source_tasks = {c.source_task for c in result.closures}
    assert source_tasks == set(ring_0_tasks)


def test_six_closure_dimensions_checked():
    assert len(CLOSURE_DIMENSIONS) == 6
    assert set(CLOSURE_DIMENSIONS) == {
        "configuration", "monitoring", "exception",
        "permission", "data", "notification",
    }


def test_ring_1_produces_concrete_derived_tasks():
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=1)
    assert len(result.closures) >= 3
    derived_tasks = {c.derived_task for c in result.closures}
    assert len(derived_tasks) >= 3


def test_concept_boundary_respected():
    ring_0_tasks = ["认证"]
    concept_boundary = ["认证"]
    result = expand_closures(ring_0_tasks=ring_0_tasks, concept_boundary=concept_boundary, max_ring=1)
    for c in result.closures:
        assert c.source_task in concept_boundary


def test_scale_reversal_detection():
    result = expand_closures(
        ring_0_tasks=["简单配置"],
        concept_boundary=["简单配置"],
        max_ring=1,
        scale_overrides={"简单配置:configuration": 2.0},
    )
    reversed_items = [c for c in result.closures if c.status == "new_domain"]
    assert len(reversed_items) > 0


def test_ring_2_only_derives_from_ring_1():
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=2)
    ring_2_items = [c for c in result.closures if c.ring == 2]
    ring_1_derived_tasks = {c.derived_task for c in result.closures if c.ring == 1}
    for item in ring_2_items:
        assert item.source_task in ring_1_derived_tasks


def test_convergence_output_decreases():
    result = expand_closures(ring_0_tasks=["认证", "下单", "支付"], concept_boundary=["认证", "下单", "支付"], max_ring=2)
    ring_1_count = len([c for c in result.closures if c.ring == 1])
    ring_2_count = len([c for c in result.closures if c.ring == 2])
    assert ring_2_count <= ring_1_count


def test_convergence_stops_on_zero_output():
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=5)
    max_ring = max((c.ring for c in result.closures), default=0)
    assert max_ring <= 3
    assert result.stopped_reason in ("zero_output", "max_ring_reached", "all_downgraded")


def test_expansion_result_has_coverage_stats():
    result = expand_closures(ring_0_tasks=["认证", "下单"], concept_boundary=["认证", "下单"], max_ring=1)
    assert result.total_ring_0 == 2
    assert result.total_ring_1 > 0
    assert result.coverage_ratio > 0.0
