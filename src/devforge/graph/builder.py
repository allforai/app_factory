"""Minimal orchestration runner using the current meta-graph skeleton."""

from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
import json
from typing import Any

from devforge.context import ContextBroker
from devforge.executors import get_executor_adapter
from devforge.graph.nodes import concept_collection_node, graph_validation_node, planning_and_shaping_node, project_scheduler_node
from devforge.graph.runtime_state import RuntimeState
from devforge.knowledge import build_specialized_knowledge, select_knowledge_for_context
from devforge.knowledge.packets import build_node_knowledge_packet
from devforge.persistence import ArtifactStore, EventStore, MemoryStore, WorkspacePersistence
from devforge.planning import apply_requirement_events, decide_retry_action
from devforge.scheduler import select_workset
from devforge.state import ExecutorPolicy, RequirementEvent, SeamState, WorkPackage, decode_snapshot


def _runtime_context_from_snapshot(snapshot: dict[str, Any]) -> RuntimeState:
    typed = decode_snapshot(snapshot)
    initiative = typed.get("initiative")
    projects = typed.get("projects", [])
    foreground_project = projects[0].project_id if projects else None
    return RuntimeState(
        workspace_id=initiative.initiative_id if initiative else "workspace",
        initiative_id=initiative.initiative_id if initiative else None,
        foreground_project=foreground_project,
    )


def _work_packages_from_snapshot(snapshot: dict[str, Any]) -> list[WorkPackage]:
    return decode_snapshot(snapshot)["work_packages"]


def _seams_from_snapshot(snapshot: dict[str, Any]) -> list[SeamState]:
    return decode_snapshot(snapshot)["seams"]


def _executor_policies_from_snapshot(snapshot: dict[str, Any]) -> dict[str, ExecutorPolicy]:
    return {policy.policy_id: policy for policy in decode_snapshot(snapshot)["executor_policies"]}


def _requirement_events_from_snapshot(snapshot: dict[str, Any]) -> list[RequirementEvent]:
    return decode_snapshot(snapshot)["requirement_events"]


def _project_for_runtime(snapshot: dict[str, Any], runtime: RuntimeState) -> dict[str, Any] | None:
    for project in snapshot.get("projects", []):
        if project["project_id"] == runtime.active_project_id:
            return project
    return None


def _maybe_seed_follow_up_work(snapshot: dict[str, Any], runtime: RuntimeState) -> bool:
    """Seed a next planning work package after repository onboarding when no work remains."""
    project = _project_for_runtime(snapshot, runtime)
    if project is None or project.get("kind") != "existing_repo":
        return False

    onboarding = _work_package_record(snapshot, "wp-repo-onboarding")
    if onboarding is None or onboarding.get("status") != "verified":
        return False

    existing = _work_package_record(snapshot, "wp-initial-work-plan")
    if existing is not None:
        return False

    snapshot.setdefault("work_packages", []).append(
        {
            "work_package_id": "wp-initial-work-plan",
            "initiative_id": onboarding.get("initiative_id"),
            "project_id": project["project_id"],
            "phase": "analysis_design",
            "domain": "core",
            "role_id": "execution_planner",
            "title": "Initial implementation backlog",
            "goal": "Turn repository onboarding findings into a concrete next-iteration backlog for continued development.",
            "status": "ready",
            "priority": max(int(onboarding.get("priority", 100)) - 10, 1),
            "executor": "codex",
            "fallback_executors": ["claude_code"],
            "inputs": ["wp-repo-onboarding"],
            "deliverables": [
                "docs/devforge/initial-work-plan.md",
                "docs/devforge/next-work-packages.json",
            ],
            "constraints": [
                "base the plan on the current repository structure",
                "propose small executable work packages with clear acceptance criteria",
            ],
            "acceptance_criteria": [
                "next iteration backlog is concrete",
                "at least three follow-up work packages are proposed",
            ],
            "depends_on": ["wp-repo-onboarding"],
            "blocks": [],
            "related_seams": [],
            "assumptions": [],
            "artifacts_created": [],
            "findings": [],
            "handoff_notes": [],
            "attempt_count": 0,
            "max_attempts": 3,
            "created_at": None,
            "updated_at": None,
        }
    )
    project.setdefault("work_package_ids", []).append("wp-initial-work-plan")
    return True


def _maybe_seed_existing_repo_implementation_work(snapshot: dict[str, Any], runtime: RuntimeState) -> bool:
    """Seed concrete implementation slices after the initial work plan is verified."""
    project = _project_for_runtime(snapshot, runtime)
    if project is None or project.get("kind") != "existing_repo":
        return False

    planning_wp = _work_package_record(snapshot, "wp-initial-work-plan")
    if planning_wp is None or planning_wp.get("status") != "verified":
        return False

    seed_ids = [
        "wp-runtime-state-persistence",
        "wp-executor-live-adapters",
        "wp-onboarding-entry-flow",
    ]
    if any(_work_package_record(snapshot, work_package_id) is not None for work_package_id in seed_ids):
        return False

    new_items = [
        {
            "work_package_id": "wp-runtime-state-persistence",
            "initiative_id": planning_wp.get("initiative_id"),
            "project_id": project["project_id"],
            "phase": "implementation",
            "domain": "core",
            "role_id": "software_engineer",
            "title": "Persist evolving runtime state",
            "goal": "Make cycle state durable so resumed runs continue from the latest verified snapshot and runtime context.",
            "status": "ready",
            "priority": 95,
            "executor": "codex",
            "fallback_executors": ["claude_code"],
            "inputs": ["wp-initial-work-plan"],
            "deliverables": [
                "src/devforge/main.py",
                "src/devforge/repl.py",
                "tests/test_main_cli.py",
            ],
            "constraints": [
                "preserve existing CLI flows",
                "avoid losing state across repeated cycles",
            ],
            "acceptance_criteria": [
                "continued cycles read the latest durable state",
                "state persistence is covered by regression tests",
            ],
            "depends_on": ["wp-initial-work-plan"],
            "blocks": ["wp-executor-live-adapters"],
            "related_seams": [],
            "assumptions": [],
            "artifacts_created": [],
            "findings": [],
            "handoff_notes": [],
            "attempt_count": 0,
            "max_attempts": 3,
            "created_at": None,
            "updated_at": None,
        },
        {
            "work_package_id": "wp-executor-live-adapters",
            "initiative_id": planning_wp.get("initiative_id"),
            "project_id": project["project_id"],
            "phase": "implementation",
            "domain": "core",
            "role_id": "software_engineer",
            "title": "Promote executor adapters toward live execution",
            "goal": "Replace stub-only progression with executor paths that can carry real work and recover from adapter mismatches.",
            "status": "ready",
            "priority": 90,
            "executor": "codex",
            "fallback_executors": ["claude_code"],
            "inputs": ["wp-initial-work-plan"],
            "deliverables": [
                "src/devforge/executors/adapters.py",
                "src/devforge/executors/subprocess_transport.py",
                "tests/test_graph_runner.py",
            ],
            "constraints": [
                "keep fallback executor switching intact",
                "surface adapter failures as actionable retry states",
            ],
            "acceptance_criteria": [
                "executor routing supports a real continuation path",
                "adapter fallback behavior is regression-tested",
            ],
            "depends_on": ["wp-runtime-state-persistence"],
            "blocks": [],
            "related_seams": [],
            "assumptions": [],
            "artifacts_created": [],
            "findings": [],
            "handoff_notes": [],
            "attempt_count": 0,
            "max_attempts": 3,
            "created_at": None,
            "updated_at": None,
        },
        {
            "work_package_id": "wp-onboarding-entry-flow",
            "initiative_id": planning_wp.get("initiative_id"),
            "project_id": project["project_id"],
            "phase": "implementation",
            "domain": "core",
            "role_id": "software_engineer",
            "title": "Make startup onboarding user-facing",
            "goal": "Guide users into initialize, switch-directory, and resume flows from the default entrypoint without requiring CLI internals.",
            "status": "ready",
            "priority": 85,
            "executor": "codex",
            "fallback_executors": ["claude_code"],
            "inputs": ["wp-initial-work-plan"],
            "deliverables": [
                "src/devforge/repl.py",
                "README.md",
                "tests/test_repl.py",
            ],
            "constraints": [
                "keep non-interactive mode script-friendly",
                "optimize for first-run discoverability",
            ],
            "acceptance_criteria": [
                "missing-runtime startup guides the user to a viable next action",
                "interactive onboarding paths are covered by tests",
            ],
            "depends_on": ["wp-runtime-state-persistence"],
            "blocks": [],
            "related_seams": [],
            "assumptions": [],
            "artifacts_created": [],
            "findings": [],
            "handoff_notes": [],
            "attempt_count": 0,
            "max_attempts": 3,
            "created_at": None,
            "updated_at": None,
        },
    ]
    snapshot.setdefault("work_packages", []).extend(new_items)
    project.setdefault("work_package_ids", []).extend(seed_ids)
    project["current_phase"] = "implementation"
    return True


def _select_knowledge_ids(snapshot: dict[str, Any], runtime: RuntimeState, selected: list[WorkPackage]) -> list[str]:
    project = _project_for_runtime(snapshot, runtime)
    if project is None:
        return []

    phase = project.get("current_phase", "analysis_design")
    domain = None
    role_id = None
    if selected:
        phase = selected[0].phase
        domain = selected[0].domain
        role_id = selected[0].role_id

    docs = select_knowledge_for_context(
        project_archetype=project.get("project_archetype", ""),
        phase=phase,
        domain=domain,
        role_id=role_id,
        preferred_ids=list(project.get("knowledge_preferences", {}).get("preferred_ids", [])),
        excluded_ids=list(project.get("knowledge_preferences", {}).get("excluded_ids", [])),
    )
    return [doc.doc_id for doc in docs]


def _build_specialized_knowledge(snapshot: dict[str, Any], runtime: RuntimeState, selected: list[WorkPackage]) -> dict[str, object]:
    project = _project_for_runtime(snapshot, runtime)
    if project is None:
        return {}

    phase = project.get("current_phase", "analysis_design")
    domain = None
    role_id = None
    if selected:
        phase = selected[0].phase
        domain = selected[0].domain
        role_id = selected[0].role_id

    return build_specialized_knowledge(
        project_archetype=project.get("project_archetype", ""),
        phase=phase,
        selected_knowledge_ids=runtime.selected_knowledge,
        domain=domain,
        role_id=role_id,
    )


def _build_node_packet(runtime: RuntimeState, selected: list[WorkPackage]) -> dict[str, object]:
    if not selected:
        return {}
    primary = selected[0]
    packet = build_node_knowledge_packet(
        phase=primary.phase,
        goal=primary.goal,
        role_id=primary.role_id,
        domain=primary.domain,
        specialized_knowledge=runtime.specialized_knowledge,
        selected_knowledge_ids=runtime.selected_knowledge,
        constraints=primary.constraints,
        acceptance=primary.acceptance_criteria,
    )
    result = asdict(packet)
    if primary.attempt_count > 0:
        result["previous_attempts"] = {
            "attempt_count": primary.attempt_count,
            "findings": [asdict(f) for f in primary.findings] if primary.findings else [],
            "handoff_notes": list(primary.handoff_notes),
            "execution_history": list(primary.execution_history),
        }
    return result


def _build_context_pull_manifest(
    snapshot: dict[str, Any],
    runtime: RuntimeState,
    *,
    artifact_store: ArtifactStore | None,
    memory_store: MemoryStore | None,
) -> dict[str, Any]:
    refs = list(runtime.node_knowledge_packet.get("deep_refs", []))
    if runtime.active_project_id:
        project_id = runtime.active_project_id
        refs.extend(
            [
                f"project://{project_id}",
                f"artifact://runtime/{project_id}/concept_brief.md",
                f"artifact://runtime/{project_id}/acceptance_goals.json",
                f"memory://project/{project_id}/latest-specialized-knowledge",
                f"memory://project/{project_id}/latest-concept-decision",
            ]
        )
    deduped_refs: list[str] = []
    for ref in refs:
        if ref and ref not in deduped_refs:
            deduped_refs.append(ref)
    broker = ContextBroker(snapshot=snapshot, artifact_store=artifact_store, memory_store=memory_store)
    return {
        "refs": deduped_refs,
        "preview": broker.preview_many(deduped_refs, mode="summary"),
    }


def _policy_for_work_package(snapshot: dict[str, Any], work_package: WorkPackage) -> ExecutorPolicy | None:
    policies = _executor_policies_from_snapshot(snapshot)
    for project in snapshot.get("projects", []):
        if project["project_id"] == work_package.project_id:
            policy_ref = project.get("executor_policy_ref")
            if policy_ref:
                policy_id = policy_ref.split("://", 1)[-1]
                return policies.get(policy_id)
    return None


def _resolve_executor_name(snapshot: dict[str, Any], work_package: WorkPackage) -> str:
    policy = _policy_for_work_package(snapshot, work_package)
    if policy is not None:
        return policy.resolve(
            work_package_id=work_package.work_package_id,
            domain=work_package.domain,
            role_id=work_package.role_id,
            phase=work_package.phase,
        )
    return work_package.executor or "python"


def _update_work_package_status(snapshot: dict[str, Any], work_package_id: str, status: str) -> None:
    for item in snapshot.get("work_packages", []):
        if item["work_package_id"] == work_package_id:
            item["status"] = status
            return


def _work_package_record(snapshot: dict[str, Any], work_package_id: str) -> dict[str, Any] | None:
    for item in snapshot.get("work_packages", []):
        if item["work_package_id"] == work_package_id:
            return item
    return None


def _append_handoff_note(snapshot: dict[str, Any], work_package_id: str, note: str) -> None:
    for item in snapshot.get("work_packages", []):
        if item["work_package_id"] == work_package_id:
            item.setdefault("handoff_notes", []).append(note)
            return


def _append_findings(snapshot: dict[str, Any], work_package_id: str, findings: list[dict[str, Any]]) -> None:
    if not findings:
        return
    for item in snapshot.get("work_packages", []):
        if item["work_package_id"] == work_package_id:
            item.setdefault("findings", []).extend(findings)
            return


def _record_execution_attempt(snapshot: dict[str, Any], work_package_id: str, execution_ref: dict[str, str | None]) -> None:
    item = _work_package_record(snapshot, work_package_id)
    if item is None:
        return
    item["attempt_count"] = item.get("attempt_count", 0) + 1
    item["last_execution_ref"] = execution_ref
    item.setdefault("execution_history", []).append(execution_ref)


def _apply_executor_result(
    snapshot: dict[str, Any],
    result: dict[str, Any],
    *,
    retry_context: dict[str, Any] | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> None:
    work_package_id = result["work_package_id"]
    execution_ref = result.get("execution_ref", {})
    _record_execution_attempt(snapshot, work_package_id, execution_ref)
    _append_handoff_note(snapshot, work_package_id, result["summary"])
    _append_findings(snapshot, work_package_id, result.get("findings", []))

    if result["status"] == "completed":
        _update_work_package_status(snapshot, work_package_id, "verified")
    elif result["status"] == "partial":
        _update_work_package_status(snapshot, work_package_id, "completed")
    else:
        item = _work_package_record(snapshot, work_package_id)
        if item is None:
            _update_work_package_status(snapshot, work_package_id, "failed")
            return
        retry_decision = decide_retry_action(item, result, context=retry_context, llm_preferences=llm_preferences)
        item["retry_action"] = retry_decision.action
        item["retry_reason"] = retry_decision.reason
        item["retry_source"] = retry_decision.source
        item["retry_confidence"] = retry_decision.confidence
        item["retry_notes"] = retry_decision.notes
        if retry_decision.action == "switch_executor":
            item["executor"] = retry_decision.next_executor
            _update_work_package_status(snapshot, work_package_id, "ready")
        elif retry_decision.action == "requeue":
            _update_work_package_status(snapshot, work_package_id, "ready")
        elif retry_decision.action == "block":
            _update_work_package_status(snapshot, work_package_id, "blocked")
        elif retry_decision.action == "replan":
            item["replan_required"] = True
            _update_work_package_status(snapshot, work_package_id, "blocked")
        else:
            _update_work_package_status(snapshot, work_package_id, "failed")


def _dispatch_selected_work(
    selected: list[WorkPackage],
    runtime: RuntimeState,
    snapshot: dict[str, Any],
    *,
    artifact_store: ArtifactStore | None,
    memory_store: MemoryStore | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dispatches: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    broker = ContextBroker(snapshot=snapshot, artifact_store=artifact_store, memory_store=memory_store)
    context_pull_manifest = _build_context_pull_manifest(
        snapshot,
        runtime,
        artifact_store=artifact_store,
        memory_store=memory_store,
    )

    for wp in selected:
        executor_name = _resolve_executor_name(snapshot, wp)
        adapter = get_executor_adapter(executor_name)
        project = _project_for_runtime(snapshot, runtime) or {}
        base_runtime_context = {
            "cycle_id": runtime.cycle_id,
            "initiative_id": runtime.initiative_id,
            "project_id": runtime.active_project_id,
            "working_dir": ".",
            "project_archetype": project.get("project_archetype"),
            "project_pull_policy_overrides": project.get("pull_policy_overrides", []),
            "project_llm_preferences": runtime.project_llm_preferences,
            "project_knowledge_preferences": runtime.project_knowledge_preferences,
            "node_knowledge_packet": runtime.node_knowledge_packet,
            "context_pull_manifest": context_pull_manifest,
        }
        pull_strategy = adapter.default_pull_strategy(wp, base_runtime_context)
        pulled_context = [
            asdict(item)
            for item in adapter.pull_context(
                pull_strategy.get("refs", []),
                broker=broker,
                mode=pull_strategy.get("mode", "summary"),
                budget=pull_strategy.get("budget"),
            )
        ]
        _update_work_package_status(snapshot, wp.work_package_id, "running")
        dispatch = adapter.dispatch(
            wp,
            {
                **base_runtime_context,
                "pull_strategy": pull_strategy,
                "pulled_context": pulled_context,
            },
        )
        dispatches.append(asdict(dispatch))

        if not dispatch.accepted:
            final_result = dispatch.metadata.get("submission_receipt", {}).get("metadata", {}).get("final_result")
            raw_results.append(
                final_result
                or {
                    "execution_id": dispatch.execution_id,
                    "work_package_id": wp.work_package_id,
                    "cycle_id": runtime.cycle_id,
                    "status": "failed",
                    "summary": dispatch.message,
                    "findings": [],
                }
            )
            continue

        runtime.running_queue.append(wp.work_package_id)
        final_result = dispatch.metadata.get("submission_receipt", {}).get("metadata", {}).get("final_result")
        raw_results.append(
            final_result
            or {
                "execution_id": dispatch.execution_id,
                "work_package_id": wp.work_package_id,
                "cycle_id": runtime.cycle_id,
                "status": "completed",
                "summary": "stub execution completed",
                "findings": [],
            }
        )

    return dispatches, raw_results


def _verify_results(
    selected: list[WorkPackage],
    raw_results: list[dict[str, Any]],
    runtime: RuntimeState,
    snapshot: dict[str, Any],
    *,
    retry_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    selected_by_id = {wp.work_package_id: wp for wp in selected}

    for raw_result in raw_results:
        work_package_id = raw_result["work_package_id"]
        wp = selected_by_id[work_package_id]
        adapter = get_executor_adapter(_resolve_executor_name(snapshot, wp))
        result = asdict(adapter.normalize_result(raw_result))
        results.append(result)
        runtime.recent_executor_results.append(result["execution_id"])
        merged_retry_context = dict(retry_context or {})
        merged_retry_context.update(
            _retry_context_for_work_package(
                snapshot,
                runtime,
                work_package_id,
                requirement_patch_applied=bool((retry_context or {}).get("requirement_patch_applied")),
            )
        )
        _apply_executor_result(
            snapshot,
            result,
            retry_context=merged_retry_context,
            llm_preferences=runtime.project_llm_preferences,
        )

    if selected:
        runtime.running_queue = []

    return results


def _status_for_work_package(snapshot: dict[str, Any], work_package_id: str) -> str | None:
    item = _work_package_record(snapshot, work_package_id)
    if item is None:
        return None
    return item.get("status")


def _retry_context_for_work_package(
    snapshot: dict[str, Any],
    runtime: RuntimeState,
    work_package_id: str,
    *,
    requirement_patch_applied: bool,
) -> dict[str, Any]:
    work_package = _work_package_record(snapshot, work_package_id) or {}
    related_seams = [
        seam
        for seam in snapshot.get("seams", [])
        if seam.get("seam_id") in work_package.get("related_seams", [])
    ]
    relevant_requirement_events = [
        event
        for event in snapshot.get("requirement_events", [])
        if work_package_id in event.get("affected_work_packages", [])
    ]
    return {
        "requirement_patch_applied": requirement_patch_applied,
        "specialized_knowledge": runtime.specialized_knowledge,
        "node_knowledge_packet": runtime.node_knowledge_packet,
        "related_seams": related_seams,
        "requirement_events": relevant_requirement_events,
        "executor_history": work_package.get("execution_history", []),
        "active_project_id": runtime.active_project_id,
        "cycle_id": runtime.cycle_id,
    }


def _emit_event(
    events: list[dict[str, Any]],
    event_type: str,
    scope_id: str,
    payload: dict[str, Any],
    *,
    cycle_token: str,
) -> None:
    events.append(
        {
            "event_id": f"{cycle_token}:{event_type}:{scope_id}:{len(events) + 1}",
            "event_type": event_type,
            "scope_id": scope_id,
            "payload": payload,
        }
    )


def _execution_ref_payload(
    *,
    cycle_id: str | None,
    work_package_id: str,
    executor: str,
    execution_id: str,
) -> dict[str, str | None]:
    return {
        "cycle_id": cycle_id,
        "work_package_id": work_package_id,
        "executor": executor,
        "execution_id": execution_id,
    }


def _persist_runtime_context(
    runtime: RuntimeState,
    *,
    artifact_store: ArtifactStore | None,
    memory_store: MemoryStore | None,
) -> None:
    if runtime.active_project_id is None:
        return
    project_id = runtime.active_project_id
    cycle_id = runtime.cycle_id or "cycle-unknown"
    if artifact_store is not None and runtime.specialized_knowledge:
        artifact_store.write_text(
            f"runtime/{project_id}/specialized_knowledge.json",
            json.dumps(runtime.specialized_knowledge, ensure_ascii=False, indent=2),
        )
        artifact_store.write_text(
            f"runtime/{project_id}/{cycle_id}/specialized_knowledge.json",
            json.dumps(runtime.specialized_knowledge, ensure_ascii=False, indent=2),
        )
    if artifact_store is not None and runtime.concept_decision:
        artifact_store.write_text(
            f"runtime/{project_id}/concept_decision.json",
            json.dumps(runtime.concept_decision, ensure_ascii=False, indent=2),
        )
        artifact_store.write_text(
            f"runtime/{project_id}/{cycle_id}/concept_decision.json",
            json.dumps(runtime.concept_decision, ensure_ascii=False, indent=2),
        )
    if artifact_store is not None and runtime.node_knowledge_packet:
        artifact_store.write_text(
            f"runtime/{project_id}/node_knowledge_packet.json",
            json.dumps(runtime.node_knowledge_packet, ensure_ascii=False, indent=2),
        )
        artifact_store.write_text(
            f"runtime/{project_id}/{cycle_id}/node_knowledge_packet.json",
            json.dumps(runtime.node_knowledge_packet, ensure_ascii=False, indent=2),
        )
    if memory_store is not None and runtime.specialized_knowledge:
        memory_store.save_memory(
            f"project/{project_id}",
            "latest-specialized-knowledge",
            json.dumps(runtime.specialized_knowledge, ensure_ascii=False, indent=2),
            metadata={"kind": "specialized_knowledge", "cycle_id": cycle_id},
        )
        memory_store.save_memory(
            f"project/{project_id}",
            f"{cycle_id}-specialized-knowledge",
            json.dumps(runtime.specialized_knowledge, ensure_ascii=False, indent=2),
            metadata={"kind": "specialized_knowledge", "cycle_id": cycle_id},
        )
    if memory_store is not None and runtime.concept_decision:
        memory_store.save_memory(
            f"project/{project_id}",
            "latest-concept-decision",
            json.dumps(runtime.concept_decision, ensure_ascii=False, indent=2),
            metadata={"kind": "concept_decision", "cycle_id": cycle_id},
        )
        memory_store.save_memory(
            f"project/{project_id}",
            f"{cycle_id}-concept-decision",
            json.dumps(runtime.concept_decision, ensure_ascii=False, indent=2),
            metadata={"kind": "concept_decision", "cycle_id": cycle_id},
        )
    concept_brief = _render_concept_brief(runtime)
    acceptance_goals = _derive_acceptance_goals(runtime)
    if artifact_store is not None and concept_brief:
        artifact_store.write_text(
            f"runtime/{project_id}/concept_brief.md",
            concept_brief,
        )
        artifact_store.write_text(
            f"runtime/{project_id}/{cycle_id}/concept_brief.md",
            concept_brief,
        )
    if artifact_store is not None and acceptance_goals:
        artifact_store.write_text(
            f"runtime/{project_id}/acceptance_goals.json",
            json.dumps(acceptance_goals, ensure_ascii=False, indent=2),
        )
        artifact_store.write_text(
            f"runtime/{project_id}/{cycle_id}/acceptance_goals.json",
            json.dumps(acceptance_goals, ensure_ascii=False, indent=2),
        )
    if memory_store is not None and concept_brief:
        memory_store.save_memory(
            f"project/{project_id}",
            "latest-concept-brief",
            concept_brief,
            metadata={"kind": "concept_brief", "cycle_id": cycle_id},
        )
        memory_store.save_memory(
            f"project/{project_id}",
            f"{cycle_id}-concept-brief",
            concept_brief,
            metadata={"kind": "concept_brief", "cycle_id": cycle_id},
        )
    if memory_store is not None and acceptance_goals:
        serialized_goals = json.dumps(acceptance_goals, ensure_ascii=False, indent=2)
        memory_store.save_memory(
            f"project/{project_id}",
            "latest-acceptance-goals",
            serialized_goals,
            metadata={"kind": "acceptance_goals", "cycle_id": cycle_id},
        )
        memory_store.save_memory(
            f"project/{project_id}",
            f"{cycle_id}-acceptance-goals",
            serialized_goals,
            metadata={"kind": "acceptance_goals", "cycle_id": cycle_id},
        )


def _render_concept_brief(runtime: RuntimeState) -> str:
    if not runtime.concept_decision:
        return ""
    focus_areas = runtime.concept_decision.get("focus_areas", [])
    questions = runtime.concept_decision.get("questions", [])
    rationale = runtime.concept_decision.get("rationale", "")
    notes = runtime.concept_decision.get("notes", [])
    sections = [
        "# Concept Brief",
        "",
        f"Goal: {runtime.concept_decision.get('goal', '')}",
        f"Phase: {runtime.concept_decision.get('phase', runtime.current_phase or '')}",
        "",
        "## Focus Areas",
    ]
    sections.extend(f"- {item}" for item in focus_areas)
    sections.extend(
        [
            "",
            "## Discovery Questions",
        ]
    )
    sections.extend(f"- {item}" for item in questions)
    if rationale:
        sections.extend(["", "## Rationale", rationale])
    if notes:
        sections.extend(["", "## Notes"])
        sections.extend(f"- {item}" for item in notes)
    return "\n".join(sections).strip() + "\n"


def _derive_acceptance_goals(runtime: RuntimeState) -> list[str]:
    if not runtime.concept_decision:
        return []
    goals = [f"clarify {item}" for item in runtime.concept_decision.get("focus_areas", [])]
    concept_goal = runtime.concept_decision.get("goal")
    if concept_goal:
        goals.insert(0, concept_goal)
    deduped: list[str] = []
    for goal in goals:
        if goal and goal not in deduped:
            deduped.append(goal)
    return deduped


def _persist_snapshot(
    snapshot: dict[str, Any],
    runtime: RuntimeState,
    persistence: WorkspacePersistence,
) -> None:
    if persistence.snapshot_store is None:
        return

    workspace_id = runtime.workspace_id or "workspace"
    history_prefix = f"workspace-{workspace_id}-cycle-"
    existing_history = [
        name for name in persistence.snapshot_store.list_snapshots() if name.startswith(history_prefix)
    ]
    cycle_index = len(existing_history) + 1
    cycle_id = runtime.cycle_id or f"cycle-{cycle_index:04d}"
    history_name = f"workspace-{workspace_id}-{cycle_id}"

    persistence.snapshot_store.save_snapshot("latest", snapshot)
    persistence.snapshot_store.save_snapshot(f"workspace-{workspace_id}-latest", snapshot)
    persistence.snapshot_store.save_snapshot(history_name, snapshot)

    if runtime.initiative_id is not None:
        persistence.snapshot_store.save_snapshot(f"initiative-{runtime.initiative_id}-latest", snapshot)

    if runtime.active_project_id is not None:
        persistence.snapshot_store.save_snapshot(f"project-{runtime.active_project_id}-latest", snapshot)


def _next_cycle_id(
    runtime: RuntimeState,
    persistence: WorkspacePersistence,
    event_store: EventStore | None,
) -> str:
    workspace_id = runtime.workspace_id or "workspace"
    if persistence.snapshot_store is not None:
        history_prefix = f"workspace-{workspace_id}-cycle-"
        existing_history = [
            name for name in persistence.snapshot_store.list_snapshots() if name.startswith(history_prefix)
        ]
        return f"cycle-{len(existing_history) + 1:04d}"
    if event_store is not None:
        completed_cycles = event_store.list_events(event_type="cycle_completed", scope_id=workspace_id)
        return f"cycle-{len(completed_cycles) + 1:04d}"
    return "cycle-0001"


def run_cycle(
    snapshot: dict[str, Any],
    *,
    persistence: WorkspacePersistence | None = None,
    event_store: EventStore | None = None,
    artifact_store: ArtifactStore | None = None,
    memory_store: MemoryStore | None = None,
) -> dict[str, Any]:
    """Execute one minimal orchestration cycle against a snapshot."""
    persistence = persistence or WorkspacePersistence()
    event_store = event_store or persistence.event_store
    artifact_store = artifact_store or persistence.artifact_store
    memory_store = memory_store or persistence.memory_store

    updated_snapshot = deepcopy(snapshot)
    cycle_events: list[dict[str, Any]] = []
    requirement_events = _requirement_events_from_snapshot(updated_snapshot)
    pending_events = [event for event in requirement_events if event.patch_status != "applied"]
    runtime = _runtime_context_from_snapshot(updated_snapshot)
    cycle_token = _next_cycle_id(runtime, persistence, event_store)
    runtime.cycle_id = cycle_token
    if pending_events:
        updated_snapshot = apply_requirement_events(updated_snapshot, pending_events)
        for event in pending_events:
            _emit_event(
                cycle_events,
                "requirement_patch_applied",
                event.requirement_event_id,
                {
                    "initiative_id": event.initiative_id,
                    "project_ids": event.project_ids,
                    "type": event.type,
                    "cycle_id": cycle_token,
                },
                cycle_token=cycle_token,
            )
    runtime = project_scheduler_node(runtime)

    work_packages = _work_packages_from_snapshot(updated_snapshot)
    seams = _seams_from_snapshot(updated_snapshot)
    selected = select_workset(work_packages, seams, limit=3)
    if not selected and _maybe_seed_follow_up_work(updated_snapshot, runtime):
        work_packages = _work_packages_from_snapshot(updated_snapshot)
        selected = select_workset(work_packages, seams, limit=3)
    if not selected and _maybe_seed_existing_repo_implementation_work(updated_snapshot, runtime):
        work_packages = _work_packages_from_snapshot(updated_snapshot)
        selected = select_workset(work_packages, seams, limit=3)
    knowledge_ids = _select_knowledge_ids(updated_snapshot, runtime, selected)
    runtime.selected_knowledge = knowledge_ids
    project = _project_for_runtime(updated_snapshot, runtime) or {}
    runtime.project_llm_preferences = dict(project.get("llm_preferences", {}))
    runtime.project_knowledge_preferences = dict(project.get("knowledge_preferences", {}))
    specialized_knowledge = _build_specialized_knowledge(updated_snapshot, runtime, selected)
    runtime.specialized_knowledge = specialized_knowledge
    runtime = concept_collection_node(
        runtime,
        project=project,
        knowledge_ids=knowledge_ids,
        specialized_knowledge=specialized_knowledge,
        llm_preferences=runtime.project_llm_preferences,
    )
    node_knowledge_packet = _build_node_packet(runtime, selected)

    runtime = planning_and_shaping_node(
        runtime,
        [wp.work_package_id for wp in selected],
        project=project,
        knowledge_ids=knowledge_ids,
        specialized_knowledge=specialized_knowledge,
        node_knowledge_packet=node_knowledge_packet,
        llm_preferences=runtime.project_llm_preferences,
    )
    runtime = graph_validation_node(runtime)
    _persist_runtime_context(runtime, artifact_store=artifact_store, memory_store=memory_store)

    dispatches, raw_results = _dispatch_selected_work(
        selected,
        runtime,
        updated_snapshot,
        artifact_store=artifact_store,
        memory_store=memory_store,
    )
    for dispatch in dispatches:
        _emit_event(
            cycle_events,
            "work_package_dispatched",
            dispatch["work_package_id"],
            {
                "executor": dispatch["executor"],
                "accepted": dispatch["accepted"],
                "execution_id": dispatch["execution_id"],
                "cycle_id": cycle_token,
                "execution_ref": _execution_ref_payload(
                    cycle_id=cycle_token,
                    work_package_id=dispatch["work_package_id"],
                    executor=dispatch["executor"],
                    execution_id=dispatch["execution_id"],
                ),
            },
            cycle_token=cycle_token,
        )
    results = _verify_results(
        selected,
        raw_results,
        runtime,
        updated_snapshot,
        retry_context={"requirement_patch_applied": bool(pending_events)},
    )
    for result in results:
        _emit_event(
            cycle_events,
            "executor_result_normalized",
            result["work_package_id"],
            {
                "executor": result["executor"],
                "status": result["status"],
                "execution_id": result["execution_id"],
                "cycle_id": cycle_token,
                "execution_ref": result["execution_ref"],
            },
            cycle_token=cycle_token,
        )
        if _status_for_work_package(updated_snapshot, result["work_package_id"]) == "ready":
            work_package_record = _work_package_record(updated_snapshot, result["work_package_id"])
            retry_action = work_package_record.get("retry_action", "requeue") if work_package_record else "requeue"
            _emit_event(
                cycle_events,
                "work_package_requeued",
                result["work_package_id"],
                {
                    "cycle_id": cycle_token,
                    "execution_ref": result["execution_ref"],
                    "attempt_count": work_package_record.get("attempt_count", 0) if work_package_record else 0,
                    "retry_action": retry_action,
                },
                cycle_token=cycle_token,
            )
            if retry_action == "switch_executor":
                _emit_event(
                    cycle_events,
                    "work_package_executor_switched",
                    result["work_package_id"],
                    {
                        "cycle_id": cycle_token,
                        "execution_ref": result["execution_ref"],
                        "next_executor": work_package_record.get("executor") if work_package_record else None,
                    },
                    cycle_token=cycle_token,
                )
        elif _status_for_work_package(updated_snapshot, result["work_package_id"]) == "blocked":
            work_package_record = _work_package_record(updated_snapshot, result["work_package_id"])
            retry_action = work_package_record.get("retry_action", "block") if work_package_record else "block"
            event_type = "work_package_blocked"
            if retry_action == "replan":
                event_type = "work_package_replan_requested"
            _emit_event(
                cycle_events,
                event_type,
                result["work_package_id"],
                {
                    "cycle_id": cycle_token,
                    "execution_ref": result["execution_ref"],
                    "retry_action": retry_action,
                    "retry_reason": work_package_record.get("retry_reason") if work_package_record else None,
                },
                cycle_token=cycle_token,
            )
    _emit_event(
        cycle_events,
        "cycle_completed",
        runtime.workspace_id,
        {
            "initiative_id": runtime.initiative_id,
            "project_id": runtime.active_project_id,
            "selected_work_packages": [wp.work_package_id for wp in selected],
            "cycle_id": cycle_token,
        },
        cycle_token=cycle_token,
    )
    if event_store is not None:
        for event in cycle_events:
            event_store.append_event(event)
    _persist_snapshot(updated_snapshot, runtime, persistence)

    return {
        "runtime": asdict(runtime),
        "selected_work_packages": [wp.work_package_id for wp in selected],
        "dispatches": dispatches,
        "results": results,
        "events": cycle_events,
        "snapshot": updated_snapshot,
    }
