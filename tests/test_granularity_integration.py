# tests/test_granularity_integration.py
"""Integration test: granularity check before dispatch."""
from devforge.executors.granularity import validate_granularity
from devforge.state import WorkPackage

def test_oversized_package_detected_before_dispatch():
    wp = WorkPackage(work_package_id="WP-huge", initiative_id="I-1", project_id="P-1", phase="implementation", domain="backend", role_id="software_engineer", title="Huge package", goal="x " * 10000, status="ready", acceptance_criteria=["c" * 200 for _ in range(50)])
    action = validate_granularity(wp, "codex")
    assert action.action == "split"

def test_normal_package_passes_granularity():
    # Goal is ~3 000 chars to stay above the coarse-executor merge threshold
    # (5 % of 50 000 = 2 500 tokens) while remaining well under the 50 000 max.
    wp = WorkPackage(
        work_package_id="WP-normal",
        initiative_id="I-1",
        project_id="P-1",
        phase="implementation",
        domain="backend",
        role_id="software_engineer",
        title="Normal package",
        goal="implement user authentication " * 100,
        status="ready",
    )
    action = validate_granularity(wp, "claude_code")
    assert action.action == "ok"
