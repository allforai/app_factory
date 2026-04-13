"""Workflow engine: node selection, artifact reconciliation, and execution."""

from __future__ import annotations

import copy
import logging
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
from devforge.workflow.artifacts import check_artifacts
from devforge.executors.subprocess_transport import build_codex_command
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    NodeStrategy,
    TransitionEntry,
    WorkflowManifest,
    WorkflowStatus,
)
from devforge.workflow.store import (
    active_workflow_id,
    append_transition,
    read_index,
    read_manifest,
    read_node,
    write_index,
    write_manifest,
)

_log = logging.getLogger(__name__)

MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3
_META_BUS_ROOT = Path(".allforai") / "devforge"
_CODE_REPLICATE_ROOT = Path(".allforai") / "code-replicate"
_MYSKILLS_ROOT = Path("/Users/aa/workspace/myskills")
_CODE_REPLICATE_SCRIPT = _MYSKILLS_ROOT / "shared" / "scripts" / "code-replicate" / "cr_discover.py"
_CODE_REPLICATE_PYTHONPATH = str(_CODE_REPLICATE_SCRIPT.parent)
_AUDIT_CHECKLIST_REF = "knowledge/content/vault/static-analysis-checklist.md"
_DIAGNOSIS_REF = "knowledge/content/vault/diagnosis.md"


def _default_strategy(node: NodeDefinition | NodeManifestEntry) -> NodeStrategy | None:
    capability = node.get("capability", "")
    mode = node.get("mode")
    if mode == "discovery" or capability in {"discovery", "product-analysis", "reverse-concept"}:
        return "REVERSE_ANALYSIS"
    if capability in {"compile-verify", "test-verify", "product-verify", "quality-checks", "spec-compliance-verify"}:
        return "FULL_STACK_VALIDATION"
    if capability in {"translate", "generate-artifacts", "tune", "coding"}:
        return "TDD_REFACTOR"
    if capability in {"infra-design", "architecture", "governance", "pipeline-closure-verify"}:
        return "GOVERNANCE"
    return None


def resolve_node_strategy(node: NodeDefinition | NodeManifestEntry) -> NodeStrategy | None:
    return node.get("strategy") or _default_strategy(node)


def _child_nodes(manifest: WorkflowManifest, parent_id: str) -> list[NodeManifestEntry]:
    return [n for n in manifest["nodes"] if n.get("parent_node_id") == parent_id]


def _meta_node_id(kind: str, node_id: str, attempt_count: int) -> str:
    return f"{kind}-{node_id}-a{attempt_count}"


def _write_meta_node(root: Path, wf_id: str, node_def: NodeDefinition) -> None:
    from devforge.workflow.store import write_node

    write_node(root, wf_id, node_def)


def _append_manifest_node(manifest: WorkflowManifest, node_def: NodeDefinition, *, parent_node_id: str | None = None) -> None:
    manifest["nodes"].append({
        "id": node_def["id"],
        "status": "pending",
        "strategy": resolve_node_strategy(node_def),
        "depends_on": node_def.get("depends_on", []),
        "exit_artifacts": node_def.get("exit_artifacts", []),
        "executor": node_def.get("executor", "codex"),
        "mode": node_def.get("mode"),
        "parent_node_id": parent_node_id,
        "depth": 1,
        "attempt_count": 0,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
        "pid": None,
        "log_path": None,
    })


def _load_node_definition(root: Path, wf_id: str, node_id: str, fallback: NodeManifestEntry) -> NodeDefinition:
    try:
        node = read_node(root, wf_id, node_id)
    except FileNotFoundError:
        node = {
            "id": fallback["id"],
            "capability": "coding",
            "strategy": fallback.get("strategy"),
            "goal": fallback["id"],
            "exit_artifacts": fallback.get("exit_artifacts", []),
            "knowledge_refs": [],
            "executor": fallback.get("executor", "codex"),
            "mode": fallback.get("mode"),
            "depends_on": fallback.get("depends_on", []),
        }
    if "strategy" not in node:
        node["strategy"] = resolve_node_strategy(node)
    return node


def _diagnosis_ready(manifest: WorkflowManifest, node: NodeManifestEntry) -> bool:
    attempt = node.get("attempt_count", 0)
    diagnosis_id = _meta_node_id("diagnose", node["id"], attempt)
    for child in _child_nodes(manifest, node["id"]):
        if child["id"] == diagnosis_id and child.get("strategy") == "REVERSE_ANALYSIS":
            return child["status"] == "completed"
    return False


def select_next_nodes(manifest: WorkflowManifest) -> list[NodeManifestEntry]:
    """Return nodes that are ready to run (pending or retryable-failed + deps met + under concurrency limit)."""
    completed_ids = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running_count = sum(1 for n in manifest["nodes"] if n["status"] == "running")
    slots = MAX_CONCURRENT - running_count
    if slots <= 0:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] in ("pending", "failed")
        and n.get("attempt_count", 0) < MAX_ATTEMPTS
        and (n["status"] != "failed" or _diagnosis_ready(manifest, n))
        and set(n.get("depends_on", [])) <= completed_ids
    ][:slots]


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it


def _process_node_spawn(root: Path, manifest: WorkflowManifest, node: Any) -> bool:
    """Inject dynamically spawned child nodes from a completed node's spawn.json."""
    spawn_path = root / ".devforge" / "artifacts" / node["id"] / "spawn.json"
    if not spawn_path.exists():
        return False
    try:
        spawn_data = json.loads(spawn_path.read_text(encoding="utf-8"))
        new_nodes = spawn_data.get("new_nodes", [])
        existing_ids = {n["id"] for n in manifest["nodes"]}
        for new_node in new_nodes:
            if new_node["id"] in existing_ids:
                continue
            new_node["status"] = "pending"
            new_node["strategy"] = new_node.get("strategy") or _default_strategy(new_node)
            deps = new_node.get("depends_on") or []
            if node["id"] not in deps:
                deps.append(node["id"])
            new_node["depends_on"] = deps
            new_node.setdefault("parent_node_id", node["id"])
            new_node.setdefault("depth", node.get("depth", 0) + 1)
            new_node.setdefault("attempt_count", 0)
            new_node.setdefault("last_started_at", None)
            new_node.setdefault("last_completed_at", None)
            new_node.setdefault("last_error", None)
            new_node.setdefault("pid", None)
            new_node.setdefault("log_path", None)
            manifest["nodes"].append(new_node)
        spawn_path.rename(spawn_path.with_name("spawn.processed.json"))
        return True
    except Exception:
        _log.exception("Failed to process spawn.json for node %s", node["id"])
        return False


def process_all_node_spawns(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Check every completed node for spawn.json and expand the manifest accordingly."""
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node["status"] == "completed":
            _process_node_spawn(root, updated, node)
    return updated


def _collect_audit_violations(root: Path, artifacts: list[str]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for artifact in artifacts:
        artifact_path = root / artifact
        if not artifact_path.exists() or artifact_path.is_dir():
            continue
        try:
            raw = artifact_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            for key in ("architectural_smells", "audit_findings", "violations", "cross_layer_duplication", "missing_tests"):
                value = payload.get(key)
                if not value:
                    continue
                if isinstance(value, list):
                    for item in value:
                        violations.append({
                            "code": key.upper(),
                            "severity": "high",
                            "evidence": f"{artifact}: {item}",
                        })
                else:
                    violations.append({
                        "code": key.upper(),
                        "severity": "high",
                        "evidence": f"{artifact}: {value}",
                    })
    return violations


def _audit_node_outputs(root: Path, node: NodeManifestEntry, node_def: NodeDefinition) -> dict[str, Any]:
    violations = _collect_audit_violations(root, node_def.get("exit_artifacts", []))
    audit_dir = root / _META_BUS_ROOT / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    status = "needs_refactor" if violations else "pass"
    summary = "Meta-skill governance audit passed."
    if violations:
        summary = f"Meta-skill governance audit found {len(violations)} architectural issue(s)."
    audit = {
        "node_id": node["id"],
        "status": status,
        "summary": summary,
        "violations": violations,
        "strategy": resolve_node_strategy(node_def),
        "knowledge_refs": [_AUDIT_CHECKLIST_REF, "knowledge/content/vault/governance-styles.md"],
    }
    (audit_dir / f"{node['id']}.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return audit


def _ensure_meta_child(
    root: Path,
    manifest: WorkflowManifest,
    parent: NodeManifestEntry,
    node_def: NodeDefinition,
) -> list[str]:
    existing_ids = {n["id"] for n in manifest["nodes"]}
    created: list[str] = []
    strategy = resolve_node_strategy(node_def)
    attempt = parent.get("attempt_count", 0)

    if parent["status"] == "failed":
        diagnosis_id = _meta_node_id("diagnose", parent["id"], attempt)
        if diagnosis_id not in existing_ids:
            diagnosis_path = _META_BUS_ROOT / "diagnosis" / f"{parent['id']}-a{attempt}.json"
            diagnosis_node: NodeDefinition = {
                "id": diagnosis_id,
                "capability": "diagnosis",
                "strategy": "REVERSE_ANALYSIS",
                "goal": (
                    f"Diagnose why node `{parent['id']}` failed. Read the failure logs, inspect existing artifacts, "
                    f"follow the diagnosis protocol, and write a structured root-cause analysis to `{diagnosis_path}`."
                ),
                "exit_artifacts": [str(diagnosis_path)],
                "knowledge_refs": [_DIAGNOSIS_REF, "knowledge/content/vault/capabilities/discovery.md"],
                "executor": "codex",
                "mode": None,
                "depends_on": list(parent.get("depends_on", [])),
            }
            _write_meta_node(root, manifest["id"], diagnosis_node)
            _append_manifest_node(manifest, diagnosis_node, parent_node_id=parent["id"])
            created.append(diagnosis_id)

    if parent["status"] == "completed" and strategy in {"FULL_STACK_VALIDATION", "TDD_REFACTOR"}:
        verify_id = _meta_node_id("verify", parent["id"], attempt)
        if verify_id not in existing_ids:
            verify_path = _META_BUS_ROOT / "verification" / f"{parent['id']}-a{attempt}.json"
            verify_node: NodeDefinition = {
                "id": verify_id,
                "capability": "full-stack-validation",
                "strategy": "FULL_STACK_VALIDATION",
                "goal": (
                    f"Perform deterministic verification for node `{parent['id']}`. Validate the artifacts "
                    f"produced by this node, inspect seams, and write the verification result to `{verify_path}`."
                ),
                "exit_artifacts": [str(verify_path)],
                "knowledge_refs": [
                    "knowledge/content/vault/capabilities/compile-verify.md",
                    "knowledge/content/vault/capabilities/test-verify.md",
                    "knowledge/content/vault/capabilities/spec-compliance-verify.md",
                ],
                "executor": "codex",
                "mode": None,
                "depends_on": list(parent.get("depends_on", [])),
            }
            _write_meta_node(root, manifest["id"], verify_node)
            _append_manifest_node(manifest, verify_node, parent_node_id=parent["id"])
            created.append(verify_id)

    if parent["status"] == "needs_refactor":
        refactor_id = _meta_node_id("refactor", parent["id"], attempt)
        if refactor_id not in existing_ids:
            audit_path = _META_BUS_ROOT / "audits" / f"{parent['id']}.json"
            refactor_path = _META_BUS_ROOT / "refactors" / f"{parent['id']}-a{attempt}.json"
            refactor_node: NodeDefinition = {
                "id": refactor_id,
                "capability": "refactor",
                "strategy": "TDD_REFACTOR",
                "goal": (
                    f"Rectify the governance violations for node `{parent['id']}`. Read `{audit_path}`, apply "
                    f"the static-analysis checklist, preserve or add tests, and write a short refactor summary to `{refactor_path}`."
                ),
                "exit_artifacts": [str(refactor_path)],
                "knowledge_refs": [_AUDIT_CHECKLIST_REF, "knowledge/content/vault/capabilities/design-to-spec.md"],
                "executor": "codex",
                "mode": None,
                "depends_on": list(parent.get("depends_on", [])),
            }
            _write_meta_node(root, manifest["id"], refactor_node)
            _append_manifest_node(manifest, refactor_node, parent_node_id=parent["id"])
            created.append(refactor_id)

    return created


def apply_strategy_postprocessing(
    root: Path,
    manifest: WorkflowManifest,
    node: NodeManifestEntry,
    node_def: NodeDefinition,
) -> list[str]:
    if "strategy" not in node:
        node["strategy"] = resolve_node_strategy(node_def)
    spawned: list[str] = []
    if node["status"] == "completed" and resolve_node_strategy(node_def) == "GOVERNANCE":
        audit = _audit_node_outputs(root, node, node_def)
        if audit["violations"]:
            node["status"] = "needs_refactor"
            node["last_error"] = audit["summary"]
    spawned.extend(_ensure_meta_child(root, manifest, node, node_def))
    return spawned


def _resolve_meta_parent_states(manifest: WorkflowManifest) -> None:
    for node in manifest["nodes"]:
        if node["status"] == "needs_refactor":
            children = _child_nodes(manifest, node["id"])
            if children and all(child["status"] == "completed" for child in children if child["id"].startswith("refactor-")):
                node["status"] = "completed"
                node["last_error"] = None
                node["last_completed_at"] = _now()


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk.

    For running nodes with a pid, also checks process liveness:
    - Process alive → leave as running
    - Process dead + artifacts present → completed
    - Process dead + artifacts missing → failed

    Planning nodes (mode == "planning") are never reconciled via artifacts.
    Nodes with empty exit_artifacts are not automatically completed.
    """
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node.get("mode") in ("planning", "discovery"):
            continue  # artifact-based completion doesn't apply; spawns handled below

        if node["status"] == "running" and node.get("pid") is not None:
            if _is_process_alive(node["pid"]):
                continue
            # Process has exited — fall through to artifact check
            node_def = _load_node_definition(root, updated["id"], node["id"], node)
            if node.get("exit_artifacts", []) and check_artifacts(root, node.get("exit_artifacts", [])):
                node["status"] = "completed"
                node["last_error"] = None
                node["last_completed_at"] = _now()
                node["pid"] = None
                apply_strategy_postprocessing(root, updated, node, node_def)
            else:
                node["status"] = "failed"
                node["last_error"] = "process exited without producing exit_artifacts"
                node["last_completed_at"] = _now()
                node["pid"] = None
                apply_strategy_postprocessing(root, updated, node, node_def)
            continue

        if node["status"] in ("pending", "running") and node.get("exit_artifacts", []):
            if check_artifacts(root, node.get("exit_artifacts", [])):
                node_def = _load_node_definition(root, updated["id"], node["id"], node)
                node["status"] = "completed"
                node["last_error"] = None
                node["last_completed_at"] = _now()
                apply_strategy_postprocessing(root, updated, node, node_def)
    _resolve_meta_parent_states(updated)
    return process_all_node_spawns(root, updated)


_BUILTIN_KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge" / "content"
_DEFAULT_ATTENTION_WEIGHT = 1.0
_HIGH_ATTENTION_WEIGHT = 1.5
_CRITICAL_ATTENTION_WEIGHT = 2.5


def _load_codebase_snapshot(root: Path) -> dict[str, Any] | None:
    snapshot_path = root / ".devforge" / "artifacts" / "codebase_snapshot.json"
    if not snapshot_path.exists():
        return None
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _load_runtime_snapshot(root: Path) -> dict[str, Any] | None:
    candidates = [
        root / ".devforge" / "devforge.snapshot.json",
        root / "devforge.snapshot.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _resolve_attention_weight(node: NodeDefinition, root: Path) -> float:
    raw = node.get("attention_weight")
    if isinstance(raw, (int, float)):
        return max(float(raw), 0.1)

    snapshot = _load_runtime_snapshot(root)
    if snapshot:
        for work_package in snapshot.get("work_packages", []):
            if work_package.get("work_package_id") != node["id"]:
                continue
            candidate = work_package.get("attention_weight")
            if isinstance(candidate, (int, float)):
                return max(float(candidate), 0.1)
    return _DEFAULT_ATTENTION_WEIGHT


def _matches_core_domain(path: str, core_domains: list[str]) -> bool:
    lowered_path = path.lower()
    return any(domain.lower() in lowered_path for domain in core_domains)


def _render_push_context(snapshot: dict[str, Any], refs: list[str], *, attention_weight: float) -> str:
    structure = snapshot.get("structure", {})
    semantics = snapshot.get("semantics", {})
    modules = list(snapshot.get("modules", []))
    core_domains = list(semantics.get("core_domains", []))

    if core_domains:
        modules.sort(
            key=lambda module: (
                0 if _matches_core_domain(module.get("path", ""), core_domains) else 1,
                module.get("path", ""),
            )
        )

    module_limit = 6
    insight_limit = 5
    flow_limit = 4
    if attention_weight >= _HIGH_ATTENTION_WEIGHT:
        module_limit = 10
        insight_limit = 8
        flow_limit = 8
    if attention_weight >= _CRITICAL_ATTENTION_WEIGHT:
        module_limit = 16
        insight_limit = 12
        flow_limit = 12

    module_lines = []
    for module in modules[:module_limit]:
        exports = ", ".join(module.get("exports", [])[:6]) or "none"
        depends_on = ", ".join(module.get("depends_on", [])[:4]) or "none"
        module_lines.append(
            f"- {module.get('path', '<root>')}: {module.get('purpose', '') or 'no purpose summary'} | "
            f"exports: {exports} | depends_on: {depends_on}"
        )

    flow_lines = []
    for flow in semantics.get("key_logic_flows", [])[:flow_limit]:
        flow_lines.append(
            f"- {flow.get('from', '<unknown>')} -> {flow.get('to', '<unknown>')}: {flow.get('reason', '') or 'unspecified'}"
        )
    architecture_notes = [
        f"- {item}"
        for item in semantics.get("architectural_insights", [])[:insight_limit]
    ] or ["- none"]

    lines = [
        "Push Context Index",
        f"- attention_weight: {attention_weight:.2f}",
        f"- tech_stack: {', '.join(structure.get('tech_stack', [])) or 'unknown'}",
        f"- entry_points: {', '.join(structure.get('entry_points', [])[:8]) or 'none'}",
        f"- key_files: {', '.join(structure.get('key_files', [])[:12]) or 'none'}",
        f"- directories: {', '.join(structure.get('directories', [])[:12]) or 'none'}",
        f"- core_domains: {', '.join(core_domains[:10]) or 'none'}",
        "",
        "Module Index",
        *(module_lines or ["- none"]),
        "",
        "Architecture Notes",
        *architecture_notes,
    ]

    if flow_lines:
        lines.extend(["", "Key Logic Flows", *flow_lines])

    if refs:
        lines.extend([
            "",
            "Knowledge References",
            *[f"- {ref}" for ref in refs],
        ])

    return "\n".join(lines)


def _build_pull_tool_instructions(root: Path, wf_id: str, node: NodeDefinition) -> str:
    command = (
        "PYTHONPATH=src python -m devforge.workflow.pull_context "
        f"--root {shlex.quote(str(root))} "
        f"--wf-id {shlex.quote(wf_id)} "
        f"--node-id {shlex.quote(node['id'])} "
        "<path>"
    )
    return "\n".join([
        "Pull Tool",
        "You only have the index. Use the `pull_context(path: str) -> str` tool when you need exact implementations or artifact content.",
        "Invoke it through Bash with this exact command template:",
        command,
        "Rules:",
        "- Do not assume file contents that are not in the pushed index.",
        "- Call `pull_context` before making implementation-level claims about a file.",
        "- Prefer targeted pulls for the exact file you need instead of broad reads.",
    ])


def _load_knowledge(refs: list[str], root: Path, *, attention_weight: float = _DEFAULT_ATTENTION_WEIGHT) -> str:
    """Return push-only context built from the semantic snapshot instead of raw file contents."""
    snapshot = _load_codebase_snapshot(root)
    if snapshot is None:
        available_refs = []
        for ref in refs:
            path = root / ref
            if not path.exists():
                path = root / "src" / "devforge" / ref
            if not path.exists():
                if ref.startswith("knowledge/content/"):
                    builtin_ref = ref[len("knowledge/content/"):]
                elif ref.startswith("knowledge/"):
                    builtin_ref = ref[len("knowledge/"):]
                else:
                    builtin_ref = ref
                path = _BUILTIN_KNOWLEDGE / builtin_ref
            if path.exists():
                try:
                    available_refs.append(str(path.relative_to(root)))
                except ValueError:
                    available_refs.append(ref)
        lines = [
            "Push Context Index",
            f"- attention_weight: {attention_weight:.2f}",
            "- codebase_snapshot: missing",
            "- only reference paths are available until discovery produces .devforge/artifacts/codebase_snapshot.json",
        ]
        if available_refs:
            lines.extend(["", "Knowledge References", *[f"- {ref}" for ref in available_refs]])
        return "\n".join(lines)
    return _render_push_context(snapshot, refs, attention_weight=attention_weight)


_NON_INTERACTIVE_SUFFIX = """
---
执行约束（必须遵守）：
- 直接完成任务，不要询问任何确认或补充信息
- 若信息不足，根据已有代码和上下文做出最佳判断并继续
- 不要暂停等待用户输入
- 不要提问，不要要求审查
"""

_EXECUTOR_TIMEOUT = int(os.environ.get("DEVFORGE_EXECUTOR_TIMEOUT", "600"))


def _build_executor_cmd(node: NodeDefinition, root: Path, *, wf_id: str = "adhoc") -> tuple[list[str], str]:
    """Build the executor command and prompt for a node. Returns (cmd, executor_name)."""
    attention_weight = _resolve_attention_weight(node, root)
    knowledge = _load_knowledge(node.get("knowledge_refs", []), root, attention_weight=attention_weight)
    pull_tool = _build_pull_tool_instructions(root, wf_id, node)
    prompt = node["goal"]
    context_sections = [section for section in (knowledge, pull_tool) if section]
    if context_sections:
        prompt = f"{prompt}\n\n---\n\n" + "\n\n---\n\n".join(context_sections)
    prompt = prompt + _NON_INTERACTIVE_SUFFIX
    executor = node.get("executor", "codex")
    if executor == "codex":
        cmd = build_codex_command(prompt=prompt, working_dir=str(root))
    else:
        cmd = ["claude", "--print", "--dangerously-skip-permissions", "--allowedTools", "Bash", prompt]
    return cmd, executor


def _dispatch_node(node: NodeDefinition, root: Path) -> dict[str, Any]:
    """Call executor subprocess with node goal + knowledge content + non-interactive suffix (blocking)."""
    cmd, executor = _build_executor_cmd(node, root)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root, timeout=_EXECUTOR_TIMEOUT)
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or proc.stderr or "").strip(),
        "executor": executor,
    }


def _dispatch_node_async(
    node: NodeDefinition, root: Path, wf_id: str, started_at: str,
) -> tuple[subprocess.Popen, Path]:
    """Start executor subprocess non-blocking. Returns (process, log_path)."""
    cmd, executor = _build_executor_cmd(node, root, wf_id=wf_id)

    runs_dir = root / ".devforge" / "workflows" / wf_id / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = started_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")[:15]
    log_path = runs_dir / f"{node['id']}.{ts_slug}.log"

    log_path.write_text("\n".join([
        f"node:       {node['id']}",
        f"executor:   {executor}",
        f"started_at: {started_at}",
        f"exit_code:  (running...)",
        f"---",
    ]), encoding="utf-8")

    log_fh = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd, cwd=root,
        stdout=log_fh, stderr=subprocess.STDOUT,
        text=True,
    )
    log_fh.close()
    return proc, log_path


def _dispatch_planning_node_with_tools(
    node: NodeDefinition, root: Path, wf_id: str,
) -> dict[str, Any]:
    """Run a planning node with full claude code tool access.

    Claude reads the codebase and writes pending_plan.json directly.
    """
    plan_path = root / ".devforge" / "workflows" / wf_id / "pending_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = f"""{node['goal']}

## Your task as planner

You have full access to the codebase at {root}. Before planning:
1. Run: ls -la {root} to see project structure
2. Read key files: README.md, pyproject.toml/package.json/go.mod (whichever exists), any existing source directories
3. Check if {root}/.devforge/artifacts/codebase_snapshot.json exists and read it for context from previous runs

Then create the execution plan and write it as JSON to this exact path:
{plan_path}

The JSON must have this structure:
{{"nodes": [{{"id": "node-id-slug", "capability": "coding", "goal": "Self-contained goal with exact file paths, function signatures, no ambiguity", "exit_artifacts": ["relative/path/to/output.py"], "knowledge_refs": [], "executor": "claude_code", "mode": null, "depends_on": ["other-node-id"]}}], "summary": "One sentence summary of the plan"}}

Rules:
- Each node goal must be fully self-contained (no "as discussed above" references)
- exit_artifacts paths are relative to {root}
- Use executor="claude_code" for all nodes
- depends_on must reference node ids defined in the same plan
- Write the file, don't print the JSON to stdout
"""
    prompt = prompt + _NON_INTERACTIVE_SUFFIX

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash",
        "-p", prompt,
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True,
            timeout=_EXECUTOR_TIMEOUT,
        )
        return {
            "returncode": proc.returncode,
            "output": (proc.stdout or proc.stderr or "").strip(),
            "executor": "claude_code",
            "plan_written": plan_path.exists(),
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 1, "output": f"planner timeout after {_EXECUTOR_TIMEOUT}s", "executor": "claude_code", "plan_written": False}
    except FileNotFoundError:
        return {"returncode": 1, "output": "claude not found on PATH", "executor": "claude_code", "plan_written": False}


def _build_semantic_snapshot(root: Path, source_summary: dict[str, Any]) -> dict[str, Any]:
    modules = source_summary.get("modules", [])
    module_map = {module.get("id"): module for module in modules}
    module_paths = {module.get("id"): module.get("path", "") for module in modules}
    directories = sorted({module.get("path", "").split(os.sep)[0] for module in modules if module.get("path")})

    entry_points: list[str] = []
    key_files: list[str] = []
    mapped_modules: list[dict[str, Any]] = []
    bounded_contexts: list[dict[str, str]] = []
    architectural_insights: list[str] = []

    for module in modules:
        path = module.get("path", "")
        key_file_names = module.get("key_files", [])
        for file_name in key_file_names:
            rel = str(Path(path) / file_name) if path else file_name
            key_files.append(rel)
            lowered = file_name.lower()
            if lowered.startswith(("main.", "index.", "app.", "server.", "manage.")):
                entry_points.append(rel)

        dependencies = [module_paths.get(dep, dep) for dep in module.get("dependencies", [])]
        mapped_modules.append({
            "path": path,
            "purpose": module.get("responsibility", ""),
            "exports": list(module.get("exposed_interfaces", [])),
            "depends_on": [dep for dep in dependencies if dep],
        })

        domain_role = "core" if any(token in path.lower() for token in ("core", "domain", "engine")) else "supporting"
        bounded_contexts.append({
            "name": path.replace(os.sep, ".") or module.get("id", "root"),
            "path": path,
            "role": domain_role,
        })
        if key_file_names:
            first_key = str(Path(path) / key_file_names[0]) if path else key_file_names[0]
            if dependencies:
                architectural_insights.append(
                    f"Main Entry Point found at {first_key}, depends on {', '.join(dependencies[:3])}"
                )
            else:
                architectural_insights.append(f"Main Entry Point found at {first_key}, depends on no upstream modules")

    tests = sorted(str(p.relative_to(root)) for p in root.rglob("test*.py"))
    todos: list[str] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java"}:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in ("TODO", "FIXME"):
            if marker in text:
                todos.append(f"{file_path.relative_to(root)}:{marker}")
                break

    return {
        "scanned_at": _now(),
        "root": str(root),
        "structure": {
            "directories": directories,
            "entry_points": sorted(set(entry_points)),
            "tech_stack": source_summary.get("project", {}).get("detected_stacks", []),
            "key_files": sorted(set(key_files))[:25],
        },
        "modules": mapped_modules,
        "semantics": {
            "bounded_contexts": bounded_contexts,
            "core_domains": [ctx["name"] for ctx in bounded_contexts if ctx["role"] == "core"],
            "supporting_domains": [ctx["name"] for ctx in bounded_contexts if ctx["role"] == "supporting"],
            "key_logic_flows": [
                {
                    "from": module.get("path", ""),
                    "to": module_paths.get(dep, dep),
                    "reason": module.get("responsibility", ""),
                }
                for module in modules for dep in module.get("dependencies", [])
                if module_paths.get(dep, dep)
            ],
            "architectural_insights": architectural_insights[:20],
        },
        "existing_tests": tests,
        "open_todos": todos[:50],
        "source_summary_path": str(source_summary_path := (_CODE_REPLICATE_ROOT / "source-summary.json")),
        "data_bus": ".allforai/",
    }


def _dispatch_discovery_node(
    node: NodeDefinition, root: Path,
) -> dict[str, Any]:
    """Run semantic discovery using the myskills code-replicate scanner."""
    snapshot_path = root / ".devforge" / "artifacts" / "codebase_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    source_summary_path = root / _CODE_REPLICATE_ROOT / "source-summary.json"
    source_summary_path.parent.mkdir(parents=True, exist_ok=True)
    if not _CODE_REPLICATE_SCRIPT.exists():
        return {"returncode": 1, "output": f"code-replicate script not found: {_CODE_REPLICATE_SCRIPT}", "executor": "python3"}

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{_CODE_REPLICATE_PYTHONPATH}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH") else _CODE_REPLICATE_PYTHONPATH
    )
    cmd = ["python3", str(_CODE_REPLICATE_SCRIPT), str(root), str(source_summary_path)]

    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True,
            env=env,
            timeout=_EXECUTOR_TIMEOUT,
        )
        if proc.returncode == 0 and source_summary_path.exists():
            summary = json.loads(source_summary_path.read_text(encoding="utf-8"))
            snapshot = _build_semantic_snapshot(root, summary)
            snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "returncode": proc.returncode,
            "output": (proc.stdout or proc.stderr or "").strip(),
            "executor": "python3",
        }
    except subprocess.TimeoutExpired:
        return {"returncode": 1, "output": f"discovery timeout after {_EXECUTOR_TIMEOUT}s", "executor": "python3"}
    except FileNotFoundError:
        return {"returncode": 1, "output": "python3 not found on PATH", "executor": "python3"}


def _write_run_log(root: Path, wf_id: str, node_id: str, started_at: str,
                   executor: str, returncode: int, output: str) -> Path:
    """Save executor raw output to .devforge/workflows/<wf-id>/runs/<node>.<ts>.log"""
    runs_dir = root / ".devforge" / "workflows" / wf_id / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    # Use a sortable timestamp slug from started_at
    ts_slug = started_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")[:15]
    log_path = runs_dir / f"{node_id}.{ts_slug}.log"
    lines = [
        f"node:       {node_id}",
        f"executor:   {executor}",
        f"started_at: {started_at}",
        f"exit_code:  {returncode}",
        f"---",
        output or "(no output)",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def _write_status_json(root: Path, wf_id: str, manifest: WorkflowManifest,
                       cycle_dispatched: list[str]) -> None:
    """Write .devforge/workflows/<wf-id>/status.json — machine-readable snapshot for agents."""
    completed = [n for n in manifest["nodes"] if n["status"] == "completed"]
    failed    = [n for n in manifest["nodes"] if n["status"] == "failed"]
    running   = [n for n in manifest["nodes"] if n["status"] == "running"]
    pending   = [n for n in manifest["nodes"] if n["status"] == "pending"]
    total     = len(manifest["nodes"])

    status = {
        "wf_id": wf_id,
        "goal": manifest.get("goal", ""),
        "workflow_status": manifest["workflow_status"],
        "progress": {
            "completed": len(completed),
            "failed": len(failed),
            "running": len(running),
            "pending": len(pending),
            "total": total,
        },
        "active_nodes": [n["id"] for n in running],
        "last_cycle_at": _now(),
        "last_cycle_dispatched": cycle_dispatched,
        "nodes": [
            {
                "id": n["id"],
                "status": n["status"],
                "executor": n.get("executor", "codex"),
                "attempt": n.get("attempt_count", 0),
                "depends_on": n.get("depends_on", []),
                "exit_artifacts": n.get("exit_artifacts", []),
                "started_at": n.get("last_started_at"),
                "completed_at": n.get("last_completed_at"),
                "error": n.get("last_error"),
            }
            for n in manifest["nodes"]
        ],
    }
    status_path = root / ".devforge" / "workflows" / wf_id / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile, os as _os
    fd, tmp = tempfile.mkstemp(dir=str(status_path.parent), suffix=".tmp")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(status, indent=2, ensure_ascii=False))
        _os.replace(tmp, str(status_path))
    except Exception:
        try:
            _os.unlink(tmp)
        except OSError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_index_status(root: Path, wf_id: str, status: WorkflowStatus) -> None:
    """Update the index entry status for a workflow."""
    index = read_index(root)
    for entry in index["workflows"]:
        if entry["id"] == wf_id:
            entry["status"] = status
            break
    write_index(root, index)


def run_one_cycle(root: Path) -> dict[str, Any]:
    """Execute one workflow cycle: reconcile → select → dispatch → persist."""
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return {"status": "no_active_workflow", "dispatched": []}

    try:
        manifest = read_manifest(root, wf_id)
    except FileNotFoundError:
        return {"status": "manifest_missing", "dispatched": []}

    from devforge.workflow.graph import run_workflow_cycle
    return run_workflow_cycle(root, wf_id, manifest)
