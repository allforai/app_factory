from pathlib import Path

from devforge.executors.local_runner import run_local_request


def test_run_local_request_writes_self_hosting_acceptance_report(tmp_path: Path) -> None:
    result = run_local_request(
        {
            "work_package_id": "wp-self-hosting-acceptance",
            "cycle_id": "cycle-0013",
            "deliverables": ["docs/devforge/self-hosting-acceptance.md"],
            "payload": {
                "style": "local_acceptance",
                "checks": ["acceptance references regression evidence"],
                "handoff_notes": ["network unavailable"],
                "previous_attempts": {"handoff_notes": ["executor not logged in"]},
            },
        },
        working_dir=str(tmp_path),
    )

    report_path = tmp_path / "docs" / "devforge" / "self-hosting-acceptance.md"
    assert result["summary"] == "local acceptance report generated from executor evidence"
    assert result["artifacts_created"] == ["docs/devforge/self-hosting-acceptance.md"]
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "network unavailable" in report
    assert "executor not logged in" in report
