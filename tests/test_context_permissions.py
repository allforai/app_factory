"""Tests for status-aware permission isolation in context broker."""
from devforge.context.broker import ContextBroker


def _make_snapshot_with_work_packages():
    return {
        "projects": [{"project_id": "P-1", "name": "Test", "status": "active"}],
        "work_packages": [
            {"work_package_id": "WP-done", "project_id": "P-1", "status": "verified", "goal": "completed work", "artifacts_created": ["output.py"]},
            {"work_package_id": "WP-running", "project_id": "P-1", "status": "running", "goal": "in-progress work", "artifacts_created": ["partial.py"]},
        ],
    }


def test_can_read_verified_work_package():
    broker = ContextBroker(snapshot=_make_snapshot_with_work_packages())
    result = broker.resolve_ref("workpackage://WP-done", requester_wp_id="WP-other")
    assert result is not None
    assert result.content != ""


def test_cannot_read_running_work_package():
    broker = ContextBroker(snapshot=_make_snapshot_with_work_packages())
    result = broker.resolve_ref("workpackage://WP-running", requester_wp_id="WP-other")
    assert result is None or "access_denied" in (result.content or "")


def test_can_read_own_running_work_package():
    broker = ContextBroker(snapshot=_make_snapshot_with_work_packages())
    result = broker.resolve_ref("workpackage://WP-running", requester_wp_id="WP-running")
    assert result is not None
    assert "access_denied" not in (result.content or "")


def test_completed_status_is_readable():
    snapshot = _make_snapshot_with_work_packages()
    snapshot["work_packages"].append({"work_package_id": "WP-completed", "project_id": "P-1", "status": "completed", "goal": "done but not verified"})
    broker = ContextBroker(snapshot=snapshot)
    result = broker.resolve_ref("workpackage://WP-completed", requester_wp_id="WP-other")
    assert result is not None
    assert "access_denied" not in (result.content or "")
