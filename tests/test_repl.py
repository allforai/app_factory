import json
from pathlib import Path

from devforge.main import initialize_project, main
from devforge.repl import load_session_bundle, parse_user_intent, persist_session_bundle, run_interactive_session
from devforge.session import RunRecord, SessionState, TransitionLogEntry, ViewState


def test_parse_user_intent_supports_natural_language_commands() -> None:
    assert parse_user_intent("继续").kind == "continue_cycle"
    assert parse_user_intent("状态").kind == "show_status"
    assert parse_user_intent("观察 run-1").target_run_id == "run-1"
    assert parse_user_intent("进入 run-2").kind == "attach_run"
    assert parse_user_intent("返回").kind == "detach_run"
    assert parse_user_intent("我要新增离线收藏").kind == "input_information"


def test_main_without_runtime_enters_repl_and_reports_missing_runtime(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Run 'devforge init'" in captured.out


def test_run_interactive_session_onboards_missing_runtime_in_current_directory(tmp_path) -> None:
    output: list[str] = []
    scripted_inputs = iter(["1", "退出"])

    exit_code = run_interactive_session(
        tmp_path,
        input_fn=lambda _prompt: next(scripted_inputs),
        output_fn=output.append,
    )

    assert exit_code == 0
    assert (tmp_path / ".devforge" / "devforge.snapshot.json").exists()
    joined = "\n".join(output)
    assert "No DevForge runtime found" in joined
    assert "Initialized DevForge" in joined
    assert "Current Session Status:" in joined


def test_run_interactive_session_can_switch_directory_before_loading_runtime(tmp_path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    initialize_project(target, force=True, project_name="Demo")
    output: list[str] = []
    scripted_inputs = iter(["3", str(target), "退出"])

    exit_code = run_interactive_session(
        tmp_path,
        input_fn=lambda _prompt: next(scripted_inputs),
        output_fn=output.append,
    )

    assert exit_code == 0
    joined = "\n".join(output)
    assert "No DevForge runtime found" in joined
    assert "Current Session Status:" in joined
    assert "Project: demo" in joined


def test_run_interactive_session_supports_status_runs_attach_back_and_quit(tmp_path) -> None:
    initialize_project(tmp_path, force=True, project_name="Demo")
    session = SessionState(
        session_id="session-demo",
        project_id="demo",
        active_phase="analysis_design",
        active_feature="repo onboarding",
        current_node_revision_ids=["wp-repo-onboarding"],
        recommended_next_action="Say '继续' to resume the orchestration cycle.",
        active_run_ids=["run-1"],
        mode="waiting_user",
    )
    runs = [
        RunRecord(
            run_id="run-1",
            executor="claude_code",
            title="Analyze repository",
            status="running",
            summary="working",
            latest_output="latest output",
        )
    ]
    transitions = [
        TransitionLogEntry(
            transition_id="tx-1",
            object_type="run",
            object_id="run-1",
            before="queued",
            after="running",
            reason="analysis requested",
        )
    ]
    persist_session_bundle(tmp_path, session=session, view=ViewState(), runs=runs, transitions=transitions)

    scripted_inputs = iter(["状态", "runs", "观察 run-1", "进入 run-1", "返回", "退出"])
    output: list[str] = []

    exit_code = run_interactive_session(
        tmp_path,
        input_fn=lambda _prompt: next(scripted_inputs),
        output_fn=output.append,
    )

    assert exit_code == 0
    joined = "\n".join(output)
    assert "Current Session Status:" in joined
    assert "Executor Board:" in joined
    assert "[Run Detail]" in joined
    assert "[Attached Run]" in joined
    assert "Returned to main session." in joined
    assert "Session saved. Bye." in joined


def test_run_interactive_session_continue_persists_cycle_state(tmp_path) -> None:
    initialize_project(tmp_path, force=True, project_name="Demo")
    output: list[str] = []
    scripted_inputs = iter(["继续", "退出"])

    exit_code = run_interactive_session(
        tmp_path,
        input_fn=lambda _prompt: next(scripted_inputs),
        output_fn=output.append,
    )

    assert exit_code == 0
    session, _view, runs, transitions, _snapshot = load_session_bundle(tmp_path)
    assert session.mode == "waiting_user"
    assert runs
    assert transitions
    assert any("Executor Board:" in line for line in output)
