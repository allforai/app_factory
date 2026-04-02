"""Tests for product design structural validation."""

from devforge.state.design import DomainSpec, ProductDesign, UserFlow
from devforge.planning.design_validator import validate_design, ValidationResult


def _make_design(**overrides) -> ProductDesign:
    defaults = dict(
        design_id="D-test",
        initiative_id="I-001",
        project_id="P-001",
        product_name="Test",
        problem_statement="test",
        target_users=["user"],
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", dependencies=["A"]),
        ],
        user_flows=[
            UserFlow(flow_id="F-1", name="main", role="user", steps=["step1"]),
        ],
        ring_0_tasks=["task1"],
    )
    defaults.update(overrides)
    return ProductDesign(**defaults)


def test_valid_design_passes():
    result = validate_design(_make_design())
    assert result.valid is True
    assert len(result.errors) == 0


def test_dependency_cycle_detected():
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", dependencies=["C"]),
            DomainSpec(domain_id="B", name="B", purpose="b", dependencies=["A"]),
            DomainSpec(domain_id="C", name="C", purpose="c", dependencies=["B"]),
        ],
    )
    result = validate_design(design)
    assert result.valid is False
    cycle_errors = [e for e in result.errors if e.error_type == "dependency_cycle"]
    assert len(cycle_errors) > 0


def test_missing_seam_detected():
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", outputs=["data_x"], dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", inputs=["data_x"], dependencies=["A"]),
        ],
    )
    result = validate_design(design, existing_seam_pairs=set())
    assert any(w.error_type == "missing_seam" for w in result.warnings)


def test_missing_seam_suppressed_when_seam_exists():
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", outputs=["data_x"], dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", inputs=["data_x"], dependencies=["A"]),
        ],
    )
    result = validate_design(design, existing_seam_pairs={("A", "B")})
    assert not any(w.error_type == "missing_seam" for w in result.warnings)


def test_empty_ring_0_tasks_is_error():
    design = _make_design(ring_0_tasks=[])
    result = validate_design(design)
    assert result.valid is False
    assert any(e.error_type == "empty_ring_0" for e in result.errors)


def test_no_user_flows_is_error():
    design = _make_design(user_flows=[])
    result = validate_design(design)
    assert result.valid is False
    assert any(e.error_type == "no_user_flows" for e in result.errors)


def test_iteration_fix_tracking():
    previous_issues = ["dependency_cycle"]
    design = _make_design()
    result = validate_design(design, previous_issues=previous_issues)
    assert result.valid is True
    assert "dependency_cycle" in result.resolved_issues
