"""Interactive DevForge REPL/session runtime."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys
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

    if lowered in {"continue", "c", "继续", "/continue"}:
        return UserIntent(kind="continue_cycle")
    if lowered in {"status", "s", "状态", "/status"}:
        return UserIntent(kind="show_status")
    if lowered in {"runs", "r", "任务", "/runs"}:
        return UserIntent(kind="list_runs")
    if lowered in {"wp", "nodes", "工作包", "/wp"}:
        return UserIntent(kind="list_work_packages")
    if lowered in {"back", "b", "返回", "/back"}:
        return UserIntent(kind="detach_run")
    if lowered in {"quit", "q", "exit", "退出", "/quit"}:
        return UserIntent(kind="quit_session")

    for prefix in ("observe ", "观察 ", "/observe "):
        if lowered.startswith(prefix):
            return UserIntent(kind="observe_run", target_run_id=raw.split(maxsplit=1)[1].strip())

    for prefix in ("attach ", "进入 ", "/attach "):
        if lowered.startswith(prefix):
            return UserIntent(kind="attach_run", target_run_id=raw.split(maxsplit=1)[1].strip())

    # workflow commands
    if lowered in {"wf", "/wf"}:
        return UserIntent(kind="show_workflow")
    if lowered in {"wf run", "/wf run"}:
        return UserIntent(kind="run_workflow")
    if lowered in {"wf log", "/wf log"}:
        return UserIntent(kind="log_workflow")
    if lowered in {"wf list", "/wf list"}:
        return UserIntent(kind="list_workflows")

    for prefix in ("wf confirm ", "/wf confirm "):
        if lowered.startswith(prefix):
            answer = raw[len(prefix):].strip().lower()
            return UserIntent(kind="confirm_workflow", payload={"answer": answer})

    for prefix in ("wf init ", "/wf init "):
        if lowered.startswith(prefix):
            name = raw[len(prefix):].strip()
            return UserIntent(kind="init_workflow", payload={"name": name})

    for prefix in ("wf reset ", "/wf reset "):
        if lowered.startswith(prefix):
            node_id = raw[len(prefix):].strip()
            return UserIntent(kind="reset_workflow_node", payload={"node_id": node_id})

    for prefix in ("wf switch ", "/wf switch "):
        if lowered.startswith(prefix):
            wf_id = raw[len(prefix):].strip()
            return UserIntent(kind="switch_workflow", payload={"wf_id": wf_id})

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
        recommended_next_action="c 继续 | s 状态 | wp 工作包 | r 任务 | q 退出",
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


def _render_work_packages(snapshot: dict[str, Any] | None) -> list[str]:
    if not snapshot:
        return ["No snapshot loaded."]
    wps = snapshot.get("work_packages", [])
    if not wps:
        return ["No work packages in snapshot."]
    lines = [f"Work Packages ({len(wps)}):"]
    for wp in wps:
        status = wp.get("status", "?")
        title = wp.get("title") or wp.get("work_package_id", "?")
        executor = wp.get("executor", "?")
        lines.append(f"- [{status}] {title} ({executor})")
    return lines


def _render_workflow(root: Path) -> list[str]:
    """Render active workflow DAG status."""
    from devforge.workflow.store import active_workflow_id, read_manifest
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return ["No active workflow. Use 'wf init <name>' to create one."]
    try:
        manifest = read_manifest(root, wf_id)
    except FileNotFoundError:
        return [f"Workflow {wf_id} manifest missing."]
    completed = sum(1 for n in manifest["nodes"] if n["status"] == "completed")
    total = len(manifest["nodes"])
    lines = [f"Workflow: {manifest['goal']}  [{wf_id}]", "─" * 50]
    icons = {"completed": "✅", "running": "🔄", "failed": "❌", "pending": "⏳"}
    for node in manifest["nodes"]:
        icon = icons.get(node["status"], "?")
        deps = ", ".join(node["depends_on"]) if node["depends_on"] else ""
        suffix = f"  (等待: {deps})" if deps and node["status"] == "pending" else ""
        lines.append(f"{icon} {node['id']:<20} ({node['status']}){suffix}")
    lines.append("")
    lines.append(f"进度: {completed}/{total} 节点完成")
    if completed < total:
        lines.append("输入 'wf run' 继续执行")
    return lines


def _render_workflow_log(root: Path) -> list[str]:
    """Render transition log for active workflow."""
    from devforge.workflow.store import active_workflow_id, read_transitions
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return ["No active workflow."]
    transitions = read_transitions(root, wf_id)
    if not transitions:
        return ["No transitions recorded yet."]
    lines = [f"Transition Log ({len(transitions)} entries):"]
    for t in transitions[-20:]:  # last 20
        status_icon = "✅" if t["status"] == "completed" else "❌"
        lines.append(f"{status_icon} {t['node']} | {t['started_at'][:19]} → {t['completed_at'][:19]}")
        if t["error"]:
            lines.append(f"   error: {t['error'][:80]}")
    return lines


def _render_workflow_list(root: Path) -> list[str]:
    """List all workflows in index."""
    from devforge.workflow.store import read_index
    index = read_index(root)
    if not index["workflows"]:
        return ["No workflows found. Use 'wf init <name>' to create one."]
    lines = ["Workflows:"]
    for wf in index["workflows"]:
        active = " ← active" if wf["id"] == index["active_workflow_id"] else ""
        lines.append(f"  [{wf['status']}] {wf['id']} — {wf['goal']}{active}")
    return lines


def _render_pending_plan(root: Path, wf_id: str) -> list[str]:
    """Render pending plan for user confirmation."""
    import json
    plan_path = root / ".devforge" / "workflows" / wf_id / "pending_plan.json"
    if not plan_path.exists():
        return ["No pending plan found."]
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    lines = [f"待确认计划: {data.get('summary', '')}", "─" * 50]
    for i, node in enumerate(data.get("nodes", []), 1):
        lines.append(f"{i}. {node['id']:<20} → {node['executor']}  ({node.get('goal', '')[:60]})")
    lines.append("")
    lines.append("输入 'wf confirm y' 确认 或 'wf confirm n' 拒绝重新规划")
    return lines


def _init_workflow(root: Path, name: str) -> list[str]:
    """Create a new workflow with a planner node and set it as active."""
    import re
    from datetime import datetime, timezone
    from devforge.workflow.models import NodeDefinition, WorkflowManifest
    from devforge.workflow.store import read_index, write_index, write_manifest, write_node
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name).strip("-")[:40]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    wf_id = f"wf-{slug}-{ts}"
    created_at = datetime.now(timezone.utc).isoformat()

    planner_goal = f"""分析目标并制定执行计划: {name}

要求：为每个子节点编写自包含的 goal，即：
- goal 中直接说明关键参数、路径、输出格式，执行器无需询问即可完成任务
- 不依赖执行器自行发现或向用户确认的信息
- 示例（好）："扫描 src/ 目录，将模块列表写入 .devforge/artifacts/modules.json，格式: {{"modules":[{{"name","path","description"}}]}}"
- 示例（差）："扫描代码库" — 路径和输出格式不明确，执行器可能需要交互确认

输出格式（stdout，必须是合法 JSON，无其他内容）：
{{"nodes": [{{"id": "...", "capability": "...", "goal": "...", "exit_artifacts": ["..."], "knowledge_refs": [], "executor": "codex", "mode": null, "depends_on": []}}], "summary": "..."}}
"""
    planner_node: NodeDefinition = {
        "id": "planner",
        "capability": "planning",
        "goal": planner_goal,
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "claude_code",
        "mode": "planning",
        "depends_on": [],
    }

    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": name,
        "created_at": created_at,
        "workflow_status": "planning",  # type: ignore[typeddict-item]
        "nodes": [
            {
                "id": "planner",
                "status": "pending",
                "depends_on": [],
                "exit_artifacts": [],
                "executor": "claude_code",
                "mode": "planning",
                "parent_node_id": None,
                "depth": 0,
                "attempt_count": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
            }
        ],
    }
    write_manifest(root, wf_id, manifest)
    write_node(root, wf_id, planner_node)

    index = read_index(root)
    # Pause current active workflow
    for entry in index["workflows"]:
        if entry["id"] == index.get("active_workflow_id"):
            entry["status"] = "paused"  # type: ignore[typeddict-item]
    index["workflows"].append({
        "id": wf_id,
        "goal": name,
        "status": "active",  # type: ignore[typeddict-item]
        "created_at": created_at,
    })
    index["active_workflow_id"] = wf_id
    write_index(root, index)

    return [
        f"✅ 工作流已创建: {wf_id}",
        f"目标: {name}",
        "Planner 节点已就绪。输入 'wf run' 开始规划。",
    ]


def _confirm_workflow(root: Path, answer: str) -> list[str]:
    """Handle wf confirm y|n — accept or reject the planner's plan."""
    import json
    from devforge.workflow.store import active_workflow_id, read_manifest, write_manifest
    wf_id = active_workflow_id(root)
    if not wf_id:
        return ["No active workflow."]
    manifest = read_manifest(root, wf_id)
    if manifest["workflow_status"] != "awaiting_confirm":
        return ["No pending plan to confirm. Run 'wf' to check status."]

    plan_path = root / ".devforge" / "workflows" / wf_id / "pending_plan.json"
    if not plan_path.exists():
        return ["pending_plan.json missing — cannot confirm."]

    data = json.loads(plan_path.read_text(encoding="utf-8"))

    if answer == "y":
        # Append new nodes to manifest
        for node_def in data["nodes"]:
            manifest["nodes"].append({
                "id": node_def["id"],
                "status": "pending",
                "depends_on": node_def.get("depends_on", []),
                "exit_artifacts": node_def.get("exit_artifacts", []),
                "executor": node_def.get("executor", "codex"),
                "mode": node_def.get("mode", None),
                "parent_node_id": None,
                "depth": 1,
                "attempt_count": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
            })
        plan_path.unlink()
        manifest["workflow_status"] = "running"  # type: ignore[typeddict-item]
        write_manifest(root, wf_id, manifest)
        return [
            f"✅ 计划已确认，{len(data['nodes'])} 个节点加入工作流。",
            "输入 'wf run' 开始执行。",
        ]
    elif answer == "n":
        plan_path.unlink(missing_ok=True)
        for node_def in data["nodes"]:
            node_file = root / ".devforge" / "workflows" / wf_id / "nodes" / f"{node_def['id']}.json"
            node_file.unlink(missing_ok=True)
        for node in manifest["nodes"]:
            if node["id"] == "planner":
                node["status"] = "pending"
                node["last_error"] = None
        manifest["workflow_status"] = "planning"  # type: ignore[typeddict-item]
        write_manifest(root, wf_id, manifest)
        return ["❌ 计划已拒绝，Planner 节点重置为 pending。输入 'wf run' 重新规划。"]
    else:
        return ["Usage: wf confirm y | wf confirm n"]


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
        recommended_next_action="c 继续 | s 状态 | wp 工作包 | r 任务 | q 退出",
        active_run_ids=[item.get("execution_id", "") for item in result.get("dispatches", [])],
        suspended_run_ids=[],
        last_state_transition_ids=[f"transition:{item.get('execution_id')}" for item in result.get("results", [])],
        mode="waiting_user",
    )
    runs = _runs_from_cycle(result)
    transitions = _transitions_from_cycle(result)
    return session, runs, transitions, result


def _load_or_onboard_runtime(
    root: Path,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    interactive_available: bool,
) -> tuple[Path, SessionState, ViewState, list[RunRecord], list[TransitionLogEntry], dict[str, Any]] | None:
    """Load an existing runtime or interactively onboard the user into one."""
    current_root = root
    while True:
        try:
            session, view, runs, transitions, snapshot = load_session_bundle(current_root)
            return current_root, session, view, runs, transitions, snapshot
        except FileNotFoundError:
            if not interactive_available:
                output_fn(
                    "DevForge runtime not initialized. Run 'devforge init' or 'devforge init --workspace' first."
                )
                return None

            output_fn(f"No DevForge runtime found in {current_root}.")
            output_fn("1. Initialize this directory")
            output_fn("2. Initialize this directory as a workspace")
            output_fn("3. Switch to another directory")
            output_fn("4. Quit")
            try:
                choice = input_fn("Choose 1-4 [1]: ").strip()
            except EOFError:
                return None
            except KeyboardInterrupt:
                output_fn("")
                return None
            if not choice:
                choice = "1"

            if choice == "1":
                from devforge.main import initialize_project

                result = initialize_project(current_root, force=False, workspace_mode=False)
                output_fn(f"Initialized DevForge in {current_root}.")
                output_fn(f"Project: {result['project_id']}")
                continue
            if choice == "2":
                from devforge.main import initialize_project

                result = initialize_project(current_root, force=False, workspace_mode=True)
                output_fn(f"Initialized workspace runtime in {current_root}.")
                output_fn(f"Mode: {result['mode']}")
                continue
            if choice == "3":
                try:
                    raw = input_fn("Enter directory path: ").strip()
                except EOFError:
                    return None
                except KeyboardInterrupt:
                    output_fn("")
                    return None
                if not raw:
                    output_fn("No directory entered.")
                    continue
                target = Path(raw).expanduser()
                if not target.is_absolute():
                    target = (current_root / target).resolve()
                else:
                    target = target.resolve()
                if not target.is_dir():
                    output_fn(f"Directory not found: {target}")
                    continue
                current_root = target
                continue
            if choice == "4":
                output_fn("Bye.")
                return None

            output_fn("Unsupported choice.")


def run_interactive_session(
    root: str | Path = ".",
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Run the interactive DevForge session until the user exits."""
    root_path = Path(root).resolve()
    interactive_available = (
        input_fn is not input
        or output_fn is not print
        or (sys.stdin.isatty() and sys.stdout.isatty())
    )
    loaded = _load_or_onboard_runtime(
        root_path,
        input_fn=input_fn,
        output_fn=output_fn,
        interactive_available=interactive_available,
    )
    if loaded is None:
        return 2
    root_path, session, view, runs, transitions, _snapshot = loaded

    for line in _render_status(session, transitions):
        output_fn(line)

    output_fn("")
    try:
        goal = input_fn("当前目标（直接回车继续上次）: ").strip()
    except (EOFError, KeyboardInterrupt):
        goal = ""
    if goal:
        session.recommended_next_action = f"当前目标: {goal} | c 继续 | s 状态 | wf 工作流 | q 退出"
        output_fn(f"当前目标: {goal}")
    else:
        session.recommended_next_action = "c 继续 | s 状态 | wf 工作流 | wp 工作包 | q 退出"

    # show workflow status if active
    from devforge.workflow.store import active_workflow_id
    if active_workflow_id(root_path):
        output_fn("")
        for line in _render_workflow(root_path):
            output_fn(line)
    output_fn("")

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

        if intent.kind == "list_work_packages":
            snapshot = _load_json(_snapshot_path(root_path))
            for line in _render_work_packages(snapshot):
                output_fn(line)
            continue

        if intent.kind == "show_workflow":
            for line in _render_workflow(root_path):
                output_fn(line)
            continue

        if intent.kind == "run_workflow":
            from devforge.workflow.engine import run_one_cycle
            result = run_one_cycle(root_path)
            if result["status"] == "no_active_workflow":
                output_fn("No active workflow. Use 'wf init <name>' first.")
            elif result["status"] == "manifest_missing":
                output_fn("⚠ Workflow manifest missing. Check .devforge/workflows/.")
            elif result["status"] == "awaiting_confirm":
                from devforge.workflow.store import active_workflow_id as _awf_id
                wf_id = _awf_id(root_path)
                if wf_id:
                    for line in _render_pending_plan(root_path, wf_id):
                        output_fn(line)
            elif result["status"] == "all_complete":
                output_fn("✅ Workflow complete — all nodes finished.")
            elif result["status"] == "workflow_failed":
                output_fn("❌ Workflow failed — a node exceeded maximum retry attempts.")
                for line in _render_workflow(root_path):
                    output_fn(line)
            elif result["status"] == "blocked":
                output_fn(f"⚠ Blocked — no runnable nodes. Pending: {result.get('pending', [])}")
            else:
                output_fn(f"Dispatched: {', '.join(result['dispatched'])}")
                for line in _render_workflow(root_path):
                    output_fn(line)
            continue

        if intent.kind == "init_workflow":
            name = intent.payload.get("name", "").strip() if intent.payload else ""
            if not name:
                output_fn("Usage: wf init <工作流名称>")
            else:
                for line in _init_workflow(root_path, name):
                    output_fn(line)
            continue

        if intent.kind == "confirm_workflow":
            answer = (intent.payload or {}).get("answer", "")
            for line in _confirm_workflow(root_path, answer):
                output_fn(line)
            continue

        if intent.kind == "log_workflow":
            for line in _render_workflow_log(root_path):
                output_fn(line)
            continue

        if intent.kind == "list_workflows":
            for line in _render_workflow_list(root_path):
                output_fn(line)
            continue

        if intent.kind == "reset_workflow_node":
            node_id = (intent.payload or {}).get("node_id", "")
            from devforge.workflow.store import active_workflow_id, read_manifest, write_manifest
            wf_id = active_workflow_id(root_path)
            if not wf_id:
                output_fn("No active workflow.")
            else:
                manifest = read_manifest(root_path, wf_id)
                for n in manifest["nodes"]:
                    if n["id"] == node_id:
                        n["status"] = "pending"
                        n["last_error"] = None
                        write_manifest(root_path, wf_id, manifest)
                        output_fn(f"✅ Node '{node_id}' reset to pending.")
                        output_fn("Note: if old artifact files exist, reconcile will mark it completed again — delete them first.")
                        break
                else:
                    output_fn(f"Node '{node_id}' not found in active workflow.")
            continue

        if intent.kind == "switch_workflow":
            wf_id = (intent.payload or {}).get("wf_id", "")
            from devforge.workflow.store import read_index, write_index
            index = read_index(root_path)
            ids = [w["id"] for w in index["workflows"]]
            if wf_id not in ids:
                output_fn(f"Workflow '{wf_id}' not found. Use 'wf list' to see available workflows.")
            else:
                index["active_workflow_id"] = wf_id
                write_index(root_path, index)
                output_fn(f"✅ Switched to: {wf_id}")
                for line in _render_workflow(root_path):
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
            session.recommended_next_action = "输入 '继续' 或 'c' 继续下一轮，'状态' 或 's' 查看状态，'q' 退出。"
            persist_session_bundle(root_path, session=session, view=view, runs=runs, transitions=transitions)
            continue

    return 0
