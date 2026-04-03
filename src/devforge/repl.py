"""Interactive DevForge REPL/session runtime."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from devforge.session import RunRecord, SessionState, TransitionLogEntry, UserIntent, ViewState

DEFAULT_RUNTIME_ROOT = ".devforge"
DEFAULT_SNAPSHOT_FILENAME = "devforge.snapshot.json"
DEFAULT_PROJECT_CONFIG_FILENAME = "devforge.project_config.json"
SESSION_FILENAME = "session.json"
LAST_CYCLE_FILENAME = "last_cycle.json"


def _runtime_root(root: Path) -> Path:
    return root / DEFAULT_RUNTIME_ROOT


def _snapshot_path(root: Path) -> Path:
    return _runtime_root(root) / DEFAULT_SNAPSHOT_FILENAME


def _project_config_path(root: Path) -> Path:
    return _runtime_root(root) / DEFAULT_PROJECT_CONFIG_FILENAME


def _session_path(root: Path) -> Path:
    return _runtime_root(root) / SESSION_FILENAME


def _last_cycle_path(root: Path) -> Path:
    return _runtime_root(root) / LAST_CYCLE_FILENAME


def parse_user_intent(text: str) -> UserIntent:
    """Parse simple natural-language/session commands into normalized intents."""
    raw = text.strip()
    lowered = raw.lower()

    if lowered in {"continue", "继续", "/continue"}:
        return UserIntent(kind="continue_cycle")
    if lowered in {"status", "状态", "/status"}:
        return UserIntent(kind="show_status")
    if lowered in {"runs", "任务", "/runs"}:
        return UserIntent(kind="list_runs")
    if lowered in {"back", "返回", "/back"}:
        return UserIntent(kind="detach_run")
    if lowered in {"quit", "exit", "退出", "/quit"}:
        return UserIntent(kind="quit_session")

    for prefix in ("observe ", "观察 ", "/observe "):
        if lowered.startswith(prefix):
            return UserIntent(kind="observe_run", target_run_id=raw.split(maxsplit=1)[1].strip())

    for prefix in ("attach ", "进入 ", "/attach "):
        if lowered.startswith(prefix):
            return UserIntent(kind="attach_run", target_run_id=raw.split(maxsplit=1)[1].strip())

    return UserIntent(kind="input_information", payload={"text": raw})


def _default_session_from_snapshot(snapshot: dict[str, Any]) -> SessionState:
    project = snapshot.get("projects", [{}])[0] if snapshot.get("projects") else {}
    work_packages = snapshot.get("work_packages", [])
    active_feature = work_packages[0]["title"] if work_packages else None
    current_nodes = [wp["work_package_id"] for wp in work_packages[:5]]
    return SessionState(
        session_id=f"session-{project.get('project_id', 'project')}",
        project_id=project.get("project_id", "project"),
        active_phase=project.get("current_phase"),
        active_feature=active_feature,
        current_node_revision_ids=current_nodes,
        recommended_next_action="Say '继续' to resume the orchestration cycle.",
        mode="waiting_user",
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_session_bundle(root: str | Path = ".") -> tuple[SessionState, ViewState, list[RunRecord], list[TransitionLogEntry], dict[str, Any]]:
    """Load or synthesize the interactive session bundle from runtime files."""
    root_path = Path(root).resolve()
    snapshot = _load_json(_snapshot_path(root_path))
    if snapshot is None:
        raise FileNotFoundError(f"missing runtime snapshot at {_snapshot_path(root_path)}")

    session_data = _load_json(_session_path(root_path))
    last_cycle = _load_json(_last_cycle_path(root_path)) or {}

    if session_data is None:
        session = _default_session_from_snapshot(snapshot)
        view = ViewState()
        runs: list[RunRecord] = []
        transitions: list[TransitionLogEntry] = []
    else:
        session = SessionState(**session_data.get("session", {}))
        view = ViewState(**session_data.get("view", {}))
        runs = [RunRecord(**item) for item in session_data.get("runs", [])]
        transitions = [TransitionLogEntry(**item) for item in session_data.get("transitions", [])]

    if last_cycle and not runs:
        runs = _runs_from_cycle(last_cycle)
        transitions = _transitions_from_cycle(last_cycle)

    return session, view, runs, transitions, snapshot


def persist_session_bundle(
    root: str | Path,
    *,
    session: SessionState,
    view: ViewState,
    runs: list[RunRecord],
    transitions: list[TransitionLogEntry],
    last_cycle: dict[str, Any] | None = None,
) -> None:
    """Persist the interactive session and optional last cycle payload."""
    root_path = Path(root).resolve()
    _save_json(
        _session_path(root_path),
        {
            "session": asdict(session),
            "view": asdict(view),
            "runs": [asdict(item) for item in runs],
            "transitions": [asdict(item) for item in transitions],
        },
    )
    if last_cycle is not None:
        _save_json(_last_cycle_path(root_path), last_cycle)


def _runs_from_cycle(result: dict[str, Any]) -> list[RunRecord]:
    runs: list[RunRecord] = []
    dispatches = result.get("dispatches", [])
    results_by_id = {item.get("execution_id"): item for item in result.get("results", [])}
    for dispatch in dispatches:
        execution_id = dispatch.get("execution_id", "run-unknown")
        normalized = results_by_id.get(execution_id, {})
        runs.append(
            RunRecord(
                run_id=execution_id,
                executor=dispatch.get("executor", "unknown"),
                title=dispatch.get("work_package_id", "work package"),
                status="completed" if normalized.get("status") == "completed" else "running",
                trigger_ref=dispatch.get("work_package_id"),
                related_node_ids=[dispatch.get("work_package_id")] if dispatch.get("work_package_id") else [],
                summary=normalized.get("summary", dispatch.get("message", "")),
                latest_output=json.dumps(normalized, ensure_ascii=False, indent=2) if normalized else dispatch.get("message", ""),
            )
        )
    return runs


def _transitions_from_cycle(result: dict[str, Any]) -> list[TransitionLogEntry]:
    transitions: list[TransitionLogEntry] = []
    runtime = result.get("runtime", {})
    for item in result.get("results", []):
        transitions.append(
            TransitionLogEntry(
                transition_id=f"transition:{item.get('execution_id')}",
                object_type="run",
                object_id=item.get("execution_id", "run-unknown"),
                before="running",
                after=item.get("status", "completed"),
                reason=item.get("summary", ""),
            )
        )
    if runtime.get("current_phase"):
        transitions.append(
            TransitionLogEntry(
                transition_id=f"session:{runtime.get('cycle_id', 'cycle')}",
                object_type="session",
                object_id=runtime.get("workspace_id", "workspace"),
                before="waiting_user",
                after="waiting_user",
                reason=f"cycle {runtime.get('cycle_id', 'unknown')} completed for phase {runtime.get('current_phase')}",
            )
        )
    return transitions


def _render_header(session: SessionState) -> list[str]:
    return [
        f"Project: {session.project_id}",
        f"Phase: {session.active_phase or 'unknown'}",
        f"Active Feature: {session.active_feature or 'none'}",
        f"Recommended: {session.recommended_next_action or 'No recommendation'}",
    ]


def _render_status(session: SessionState, transitions: list[TransitionLogEntry]) -> list[str]:
    lines = ["Current Session Status:"]
    lines.extend(f"- {line}" for line in _render_header(session))
    if transitions:
        lines.append("Recent Transitions:")
        for item in transitions[-3:]:
            lines.append(f"- {item.object_type} {item.object_id}: {item.before} -> {item.after} ({item.reason})")
    return lines


def _render_runs(runs: list[RunRecord]) -> list[str]:
    if not runs:
        return ["No executor runs recorded yet."]
    lines = ["Executor Board:"]
    for item in runs:
        lines.append(f"- {item.run_id} | {item.executor} | {item.status} | {item.title}")
    return lines


def _render_run_detail(run: RunRecord, *, attached: bool) -> list[str]:
    heading = "[Attached Run]" if attached else "[Run Detail]"
    return [
        heading,
        f"Run: {run.run_id}",
        f"Executor: {run.executor}",
        f"Status: {run.status}",
        f"Title: {run.title}",
        f"Trigger: {run.trigger_ref or 'n/a'}",
        f"Summary: {run.summary or 'n/a'}",
        "Latest Output:",
        run.latest_output or "(none)",
    ]


def execute_continue(root: str | Path = ".") -> tuple[SessionState, list[RunRecord], list[TransitionLogEntry], dict[str, Any]]:
    """Run one orchestration cycle using the runtime snapshot/project config."""
    from devforge.main import run_snapshot_cycle

    root_path = Path(root).resolve()
    result = run_snapshot_cycle(
        _snapshot_path(root_path),
        project_config_path=_project_config_path(root_path),
        persistence_root=_runtime_root(root_path),
    )
    runtime = result["runtime"]
    session = SessionState(
        session_id=f"session-{runtime.get('active_project_id', 'project')}",
        project_id=runtime.get("active_project_id", "project"),
        active_phase=runtime.get("current_phase"),
        active_feature=(result.get("selected_work_packages") or [None])[0],
        current_node_revision_ids=list(result.get("selected_work_packages", [])),
        recommended_next_action="You can say '状态' to inspect the latest state or '继续' to run another cycle.",
        active_run_ids=[item.get("execution_id", "") for item in result.get("dispatches", [])],
        suspended_run_ids=[],
        last_state_transition_ids=[f"transition:{item.get('execution_id')}" for item in result.get("results", [])],
        mode="waiting_user",
    )
    runs = _runs_from_cycle(result)
    transitions = _transitions_from_cycle(result)
    return session, runs, transitions, result


def run_interactive_session(
    root: str | Path = ".",
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Run the interactive DevForge session until the user exits."""
    root_path = Path(root).resolve()
    try:
        session, view, runs, transitions, _snapshot = load_session_bundle(root_path)
    except FileNotFoundError:
        output_fn(
            "DevForge runtime not initialized. Run 'devforge init' or 'devforge init --workspace' first."
        )
        return 2

    for line in _render_status(session, transitions):
        output_fn(line)

    while True:
        try:
            raw = input_fn("devforge> ")
        except EOFError:
            persist_session_bundle(root_path, session=session, view=view, runs=runs, transitions=transitions)
            return 0

        intent = parse_user_intent(raw)

        if intent.kind == "quit_session":
            persist_session_bundle(root_path, session=session, view=view, runs=runs, transitions=transitions)
            output_fn("Session saved. Bye.")
            return 0

        if intent.kind == "show_status":
            for line in _render_status(session, transitions):
                output_fn(line)
            continue

        if intent.kind == "list_runs":
            for line in _render_runs(runs):
                output_fn(line)
            continue

        if intent.kind == "observe_run":
            run = next((item for item in runs if item.run_id == intent.target_run_id), None)
            if run is None:
                output_fn(f"Run not found: {intent.target_run_id}")
                continue
            for line in _render_run_detail(run, attached=False):
                output_fn(line)
            continue

        if intent.kind == "attach_run":
            run = next((item for item in runs if item.run_id == intent.target_run_id), None)
            if run is None:
                output_fn(f"Run not found: {intent.target_run_id}")
                continue
            view.focus = "attached"
            view.attached_run_id = run.run_id
            for line in _render_run_detail(run, attached=True):
                output_fn(line)
            continue

        if intent.kind == "detach_run":
            view.focus = "main"
            view.attached_run_id = None
            output_fn("Returned to main session.")
            continue

        if intent.kind == "continue_cycle":
            session, runs, transitions, last_cycle = execute_continue(root_path)
            view.focus = "main"
            view.attached_run_id = None
            persist_session_bundle(
                root_path,
                session=session,
                view=view,
                runs=runs,
                transitions=transitions,
                last_cycle=last_cycle,
            )
            for line in _render_status(session, transitions):
                output_fn(line)
            for line in _render_runs(runs):
                output_fn(line)
            continue

        if intent.kind == "input_information":
            output_fn(
                "Information captured. Feature/requirement patch application is not wired yet; "
                "current session remains at waiting_user."
            )
            session.recommended_next_action = "Say '继续' to resume the orchestration cycle or '状态' to inspect the latest state."
            persist_session_bundle(root_path, session=session, view=view, runs=runs, transitions=transitions)
            continue

    return 0
