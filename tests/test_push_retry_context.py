"""Tests for retry context injection into push packets."""

from devforge.graph.builder import _build_node_packet
from devforge.graph.runtime_state import RuntimeState
from devforge.state import WorkPackage
from devforge.state.common import Finding


def _make_wp(attempt_count=0, findings=None, handoff_notes=None):
    return WorkPackage(
        work_package_id="WP-retry",
        initiative_id="I-1",
        project_id="P-1",
        phase="implementation",
        domain="backend",
        role_id="software_engineer",
        title="Retry WP",
        goal="implement feature",
        status="ready",
        attempt_count=attempt_count,
        findings=findings or [],
        handoff_notes=handoff_notes or [],
    )


def test_first_attempt_no_retry_context():
    wp = _make_wp(attempt_count=0)
    runtime = RuntimeState(workspace_id="W-1")
    packet = _build_node_packet(runtime, [wp])
    assert packet.get("previous_attempts") is None


def test_retry_attempt_includes_previous_findings():
    wp = _make_wp(
        attempt_count=2,
        findings=[Finding(id="F1", summary="timeout on API call", severity="high", source="codex")],
        handoff_notes=["switched from codex due to timeout"],
    )
    runtime = RuntimeState(workspace_id="W-1")
    packet = _build_node_packet(runtime, [wp])
    prev = packet.get("previous_attempts")
    assert prev is not None
    assert prev["attempt_count"] == 2
    assert len(prev["findings"]) == 1
    assert prev["findings"][0]["summary"] == "timeout on API call"
    assert "switched from codex" in prev["handoff_notes"][0]
