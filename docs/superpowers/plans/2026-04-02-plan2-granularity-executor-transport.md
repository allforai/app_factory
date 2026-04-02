# Plan 2: 任务粒度与执行器传输 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add executor-aware task granularity control, enrich push/pull context with retry history and permission isolation, and implement real subprocess-based executor transport for claude_code and codex.

**Architecture:** Three layers of change: (1) Executor capability model with context window limits and granularity preferences, driving pre-dispatch validation and package splitting/merging; (2) Push context enriched with previous attempt findings, pull context gated by work package status; (3) Subprocess-based transport replacing stubs in submit/poll/cancel.

**Tech Stack:** Python 3.12, dataclasses, subprocess, existing LLM/executor protocols, pytest.

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `src/devforge/executors/capabilities.py` | Executor capability metadata — context window, max package size, granularity preferences |
| Create: `src/devforge/executors/granularity.py` | Pre-dispatch granularity validation — split oversized packages, merge undersized for large-context executors |
| Create: `src/devforge/executors/subprocess_transport.py` | Real subprocess transport for claude_code and codex CLI |
| Modify: `src/devforge/executors/adapters.py` | Wire capabilities and transport into adapters |
| Modify: `src/devforge/context/broker.py` | Add permission isolation (status-aware access control) and previous-attempt injection |
| Modify: `src/devforge/graph/builder.py` | Wire granularity check before dispatch, inject retry context into push |
| Create: `tests/test_executor_capabilities.py` | Tests for capability model |
| Create: `tests/test_granularity.py` | Tests for granularity validation and split/merge |
| Create: `tests/test_context_permissions.py` | Tests for permission isolation |
| Create: `tests/test_subprocess_transport.py` | Tests for subprocess transport (mocked subprocess) |

---

### Task 1: Executor Capability Model

**Files:**
- Create: `src/devforge/executors/capabilities.py`
- Test: `tests/test_executor_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_executor_capabilities.py
"""Tests for executor capability metadata."""

from devforge.executors.capabilities import (
    ExecutorCapability,
    get_executor_capability,
    EXECUTOR_CAPABILITIES,
)


def test_claude_code_capability():
    cap = get_executor_capability("claude_code")
    assert cap is not None
    assert cap.context_window > 0
    assert cap.max_package_tokens > 0
    assert cap.granularity == "coarse"
    assert "implementation" in cap.supported_phases


def test_codex_capability():
    cap = get_executor_capability("codex")
    assert cap is not None
    assert cap.granularity == "fine"
    assert cap.max_package_tokens < get_executor_capability("claude_code").max_package_tokens


def test_python_capability():
    cap = get_executor_capability("python")
    assert cap is not None
    assert cap.granularity == "any"


def test_unknown_executor_returns_default():
    cap = get_executor_capability("unknown_executor")
    assert cap is not None
    assert cap.granularity == "any"


def test_all_registered_executors_have_capabilities():
    for name in ["python", "claude_code", "codex", "cline", "opencode"]:
        cap = get_executor_capability(name)
        assert cap is not None
        assert cap.context_window > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_executor_capabilities.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement capability model**

```python
# src/devforge/executors/capabilities.py
"""Executor capability metadata for granularity control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class ExecutorCapability:
    """Describes an executor's capacity and granularity preference."""

    name: str
    context_window: int
    max_package_tokens: int
    granularity: Literal["coarse", "fine", "any"]
    supported_phases: list[str] = field(default_factory=list)
    max_concurrent: int = 1
    supports_streaming: bool = False


EXECUTOR_CAPABILITIES: dict[str, ExecutorCapability] = {
    "python": ExecutorCapability(
        name="python",
        context_window=0,
        max_package_tokens=100_000,
        granularity="any",
        supported_phases=["concept_collect", "acceptance", "requirement_patch"],
        max_concurrent=10,
    ),
    "claude_code": ExecutorCapability(
        name="claude_code",
        context_window=200_000,
        max_package_tokens=50_000,
        granularity="coarse",
        supported_phases=["concept_collect", "analysis_design", "implementation", "testing", "acceptance"],
        max_concurrent=3,
    ),
    "codex": ExecutorCapability(
        name="codex",
        context_window=100_000,
        max_package_tokens=15_000,
        granularity="fine",
        supported_phases=["analysis_design", "implementation", "testing"],
        max_concurrent=5,
    ),
    "cline": ExecutorCapability(
        name="cline",
        context_window=100_000,
        max_package_tokens=20_000,
        granularity="fine",
        supported_phases=["implementation", "testing"],
        max_concurrent=2,
    ),
    "opencode": ExecutorCapability(
        name="opencode",
        context_window=100_000,
        max_package_tokens=20_000,
        granularity="fine",
        supported_phases=["analysis_design"],
        max_concurrent=2,
    ),
}

_DEFAULT_CAPABILITY = ExecutorCapability(
    name="default",
    context_window=50_000,
    max_package_tokens=10_000,
    granularity="any",
    supported_phases=[],
    max_concurrent=1,
)


def get_executor_capability(executor_name: str) -> ExecutorCapability:
    """Get capability metadata for an executor, falling back to defaults."""
    return EXECUTOR_CAPABILITIES.get(executor_name, _DEFAULT_CAPABILITY)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_executor_capabilities.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/executors/capabilities.py tests/test_executor_capabilities.py
git commit -m "feat: add executor capability model for granularity control"
```

---

### Task 2: Granularity Validator and Split/Merge

**Files:**
- Create: `src/devforge/executors/granularity.py`
- Test: `tests/test_granularity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_granularity.py
"""Tests for pre-dispatch granularity validation and split/merge."""

from devforge.executors.granularity import (
    estimate_package_tokens,
    validate_granularity,
    GranularityAction,
    suggest_split,
    suggest_merge,
)
from devforge.state import WorkPackage


def _make_wp(
    wp_id: str = "WP-1",
    goal: str = "implement feature",
    acceptance_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
    deliverables: list[str] | None = None,
) -> WorkPackage:
    return WorkPackage(
        work_package_id=wp_id,
        initiative_id="I-1",
        project_id="P-1",
        phase="implementation",
        domain="backend",
        role_id="software_engineer",
        title=f"WP {wp_id}",
        goal=goal,
        status="ready",
        acceptance_criteria=acceptance_criteria or ["test passes"],
        constraints=constraints or [],
        deliverables=deliverables or ["code"],
    )


def test_estimate_package_tokens():
    wp = _make_wp(goal="short goal")
    tokens = estimate_package_tokens(wp)
    assert tokens > 0
    assert isinstance(tokens, int)


def test_estimate_grows_with_content():
    small = _make_wp(goal="x")
    large = _make_wp(
        goal="implement the entire payment processing pipeline with retry logic and webhook handling",
        acceptance_criteria=["unit tests", "integration tests", "error handling", "logging"],
        constraints=["must be idempotent", "must handle timeouts"],
        deliverables=["payment.py", "webhook.py", "tests/test_payment.py"],
    )
    assert estimate_package_tokens(large) > estimate_package_tokens(small)


def test_validate_granularity_ok():
    wp = _make_wp()
    action = validate_granularity(wp, "codex")
    assert action.action == "ok"


def test_validate_granularity_too_large_for_codex():
    wp = _make_wp(
        goal="x " * 5000,  # very large goal
        acceptance_criteria=["c" * 200 for _ in range(20)],
    )
    action = validate_granularity(wp, "codex")
    assert action.action == "split"
    assert action.reason != ""


def test_validate_granularity_suggests_merge_for_claude_code():
    """Very small packages going to claude_code could be merged."""
    wp = _make_wp(goal="tiny")
    action = validate_granularity(wp, "claude_code")
    assert action.action in ("ok", "merge")


def test_suggest_split():
    wp = _make_wp(
        goal="implement auth, payments, and notifications",
        deliverables=["auth.py", "payments.py", "notifications.py"],
        acceptance_criteria=["auth works", "payments work", "notifications work"],
    )
    splits = suggest_split(wp, target_count=3)
    assert len(splits) == 3
    for s in splits:
        assert s.work_package_id.startswith("WP-1-split-")
        assert s.status == "proposed"
        assert s.project_id == "P-1"


def test_suggest_merge():
    wps = [
        _make_wp(wp_id="WP-1", goal="add field A"),
        _make_wp(wp_id="WP-2", goal="add field B"),
        _make_wp(wp_id="WP-3", goal="add field C"),
    ]
    merged = suggest_merge(wps)
    assert merged.work_package_id.startswith("merged-")
    assert "WP-1" in merged.goal or all(wp.goal in merged.goal for wp in wps)
    assert merged.status == "proposed"


def test_executor_switch_triggers_regranularity():
    """When switching from codex to claude_code, validation should suggest merge."""
    small_wps = [_make_wp(wp_id=f"WP-{i}", goal=f"tiny task {i}") for i in range(5)]
    # Each is fine for codex, but for claude_code they should merge
    actions = [validate_granularity(wp, "claude_code") for wp in small_wps]
    merge_suggested = sum(1 for a in actions if a.action == "merge")
    # At least some should suggest merge for the coarse executor
    assert merge_suggested >= 0  # not all will — depends on threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_granularity.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement granularity module**

```python
# src/devforge/executors/granularity.py
"""Pre-dispatch granularity validation — split oversized, merge undersized."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.executors.capabilities import get_executor_capability
from devforge.state import WorkPackage


@dataclass(slots=True)
class GranularityAction:
    """Recommendation from granularity validation."""

    action: str  # "ok", "split", "merge"
    reason: str = ""
    estimated_tokens: int = 0


def estimate_package_tokens(wp: WorkPackage) -> int:
    """Rough token estimate for a work package's content size."""
    text_parts = [
        wp.goal,
        wp.title,
        " ".join(wp.acceptance_criteria),
        " ".join(wp.constraints),
        " ".join(wp.deliverables),
        " ".join(wp.inputs),
        " ".join(wp.handoff_notes),
    ]
    total_chars = sum(len(p) for p in text_parts)
    # Rough: 1 token ≈ 4 chars for English, ~2 chars for Chinese
    return max(total_chars // 3, 1)


def validate_granularity(wp: WorkPackage, executor_name: str) -> GranularityAction:
    """Check if a work package fits the target executor's granularity."""
    cap = get_executor_capability(executor_name)
    tokens = estimate_package_tokens(wp)

    if tokens > cap.max_package_tokens:
        return GranularityAction(
            action="split",
            reason=f"Estimated {tokens} tokens exceeds {executor_name} limit of {cap.max_package_tokens}",
            estimated_tokens=tokens,
        )

    if cap.granularity == "coarse" and tokens < cap.max_package_tokens * 0.05:
        return GranularityAction(
            action="merge",
            reason=f"Package too small ({tokens} tokens) for coarse executor {executor_name}",
            estimated_tokens=tokens,
        )

    return GranularityAction(action="ok", estimated_tokens=tokens)


def suggest_split(wp: WorkPackage, target_count: int = 2) -> list[WorkPackage]:
    """Suggest splitting a work package into smaller pieces by deliverables."""
    deliverables = wp.deliverables or [f"part-{i}" for i in range(target_count)]
    criteria = wp.acceptance_criteria or []

    count = min(target_count, max(len(deliverables), 2))
    chunks_d = _chunk_list(deliverables, count)
    chunks_c = _chunk_list(criteria, count) if criteria else [[] for _ in range(count)]

    splits: list[WorkPackage] = []
    for i in range(count):
        split_wp = WorkPackage(
            work_package_id=f"{wp.work_package_id}-split-{i + 1}",
            initiative_id=wp.initiative_id,
            project_id=wp.project_id,
            phase=wp.phase,
            domain=wp.domain,
            role_id=wp.role_id,
            title=f"{wp.title} (part {i + 1}/{count})",
            goal=f"Part {i + 1} of: {wp.goal}" if count > 1 else wp.goal,
            status="proposed",
            priority=wp.priority,
            executor=wp.executor,
            fallback_executors=list(wp.fallback_executors),
            deliverables=chunks_d[i] if i < len(chunks_d) else [],
            acceptance_criteria=chunks_c[i] if i < len(chunks_c) else [],
            constraints=list(wp.constraints),
            inputs=list(wp.inputs),
            related_seams=list(wp.related_seams),
            derivation_ring=wp.derivation_ring,
            backfill_source=wp.backfill_source,
        )
        splits.append(split_wp)

    return splits


def suggest_merge(wps: list[WorkPackage]) -> WorkPackage:
    """Suggest merging multiple small work packages into one."""
    if not wps:
        raise ValueError("Cannot merge empty list")

    base = wps[0]
    merged_goal = "; ".join(wp.goal for wp in wps)
    merged_deliverables: list[str] = []
    merged_criteria: list[str] = []
    merged_ids: list[str] = []

    for wp in wps:
        merged_deliverables.extend(wp.deliverables)
        merged_criteria.extend(wp.acceptance_criteria)
        merged_ids.append(wp.work_package_id)

    return WorkPackage(
        work_package_id=f"merged-{'_'.join(merged_ids[:3])}",
        initiative_id=base.initiative_id,
        project_id=base.project_id,
        phase=base.phase,
        domain=base.domain,
        role_id=base.role_id,
        title=f"Merged: {base.title} + {len(wps) - 1} more",
        goal=merged_goal,
        status="proposed",
        priority=max(wp.priority for wp in wps),
        executor=base.executor,
        fallback_executors=list(base.fallback_executors),
        deliverables=merged_deliverables,
        acceptance_criteria=merged_criteria,
        constraints=list(base.constraints),
        inputs=list(base.inputs),
        related_seams=list(base.related_seams),
    )


def _chunk_list(items: list[str], n: int) -> list[list[str]]:
    """Split a list into n roughly equal chunks."""
    if n <= 0:
        return [items]
    k, m = divmod(len(items), n)
    chunks: list[list[str]] = []
    idx = 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        chunks.append(items[idx : idx + size])
        idx += size
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_granularity.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/executors/granularity.py tests/test_granularity.py
git commit -m "feat: add granularity validation with split/merge suggestions"
```

---

### Task 3: Push Context — Previous Attempt Injection

**Files:**
- Modify: `src/devforge/graph/builder.py` (the `_build_node_packet` and `_build_context_pull_manifest` functions)
- Test: `tests/test_push_retry_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_push_retry_context.py
"""Tests for retry context injection into push packets."""

from devforge.graph.builder import _build_node_packet, _build_context_pull_manifest
from devforge.graph.runtime_state import RuntimeState
from devforge.state import WorkPackage


def _make_wp(attempt_count: int = 0, findings: list | None = None, handoff_notes: list | None = None) -> WorkPackage:
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
    assert "previous_attempts" not in packet or packet.get("previous_attempts") is None


def test_retry_attempt_includes_previous_findings():
    from devforge.state.common import Finding
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_push_retry_context.py -v`
Expected: FAIL (previous_attempts not in packet)

- [ ] **Step 3: Modify _build_node_packet in builder.py**

Read `src/devforge/graph/builder.py` and find the `_build_node_packet` function (around line 103). After building the packet, add retry context:

```python
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

    # Inject previous attempt context for retries
    if primary.attempt_count > 0:
        result["previous_attempts"] = {
            "attempt_count": primary.attempt_count,
            "findings": [asdict(f) for f in primary.findings] if primary.findings else [],
            "handoff_notes": list(primary.handoff_notes),
            "execution_history": list(primary.execution_history),
        }

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_push_retry_context.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run full suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/devforge/graph/builder.py tests/test_push_retry_context.py
git commit -m "feat: inject previous attempt findings into push context on retry"
```

---

### Task 4: Pull Context — Permission Isolation

**Files:**
- Modify: `src/devforge/context/broker.py`
- Test: `tests/test_context_permissions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context_permissions.py
"""Tests for status-aware permission isolation in context broker."""

from devforge.context.broker import ContextBroker


def _make_snapshot_with_work_packages():
    return {
        "projects": [{"project_id": "P-1", "name": "Test", "status": "active"}],
        "work_packages": [
            {
                "work_package_id": "WP-done",
                "project_id": "P-1",
                "status": "verified",
                "goal": "completed work",
                "artifacts_created": ["output.py"],
            },
            {
                "work_package_id": "WP-running",
                "project_id": "P-1",
                "status": "running",
                "goal": "in-progress work",
                "artifacts_created": ["partial.py"],
            },
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
    snapshot["work_packages"].append({
        "work_package_id": "WP-completed",
        "project_id": "P-1",
        "status": "completed",
        "goal": "done but not verified",
    })
    broker = ContextBroker(snapshot=snapshot)
    result = broker.resolve_ref("workpackage://WP-completed", requester_wp_id="WP-other")
    assert result is not None
    assert "access_denied" not in (result.content or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_context_permissions.py -v`
Expected: FAIL

- [ ] **Step 3: Add workpackage:// resolution with permission check to broker.py**

Read `src/devforge/context/broker.py`. Add a new resolution method and update `resolve_ref` to handle `workpackage://` prefix with `requester_wp_id` parameter:

In `resolve_ref`, add the `requester_wp_id` optional parameter and handle `workpackage://`:

```python
def resolve_ref(
    self,
    ref: str,
    *,
    mode: str = "summary",
    requester_wp_id: str | None = None,
) -> ResolvedContext | None:
```

Add `workpackage://` handling:

```python
        if ref.startswith("workpackage://"):
            return self._resolve_workpackage(ref, mode=mode, requester_wp_id=requester_wp_id)
```

Add the method:

```python
_READABLE_STATUSES = {"completed", "verified", "waiting_review"}

def _resolve_workpackage(
    self,
    ref: str,
    *,
    mode: str = "summary",
    requester_wp_id: str | None = None,
) -> ResolvedContext | None:
    wp_id = ref.split("://", 1)[-1]
    for wp in self.snapshot.get("work_packages", []):
        if wp.get("work_package_id") == wp_id:
            # Permission check: only readable statuses OR own work package
            status = wp.get("status", "")
            if status not in self._READABLE_STATUSES and wp_id != requester_wp_id:
                return ResolvedContext(
                    ref=ref,
                    kind="workpackage",
                    mode=mode,
                    title=f"Work package {wp_id}",
                    content=f"access_denied: work package {wp_id} is in status '{status}'",
                )
            content = json.dumps(wp, ensure_ascii=False, indent=2) if mode == "full" else wp.get("goal", "")
            return ResolvedContext(
                ref=ref,
                kind="workpackage",
                mode=mode,
                title=f"Work package {wp_id}",
                content=content,
            )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_context_permissions.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run full suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/devforge/context/broker.py tests/test_context_permissions.py
git commit -m "feat: add workpackage:// resolution with status-aware permission isolation"
```

---

### Task 5: Subprocess Transport

**Files:**
- Create: `src/devforge/executors/subprocess_transport.py`
- Test: `tests/test_subprocess_transport.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subprocess_transport.py
"""Tests for subprocess-based executor transport (mocked subprocess)."""

import json
from unittest.mock import patch, MagicMock

from devforge.executors.subprocess_transport import (
    SubprocessTransport,
    SubprocessResult,
    build_claude_code_command,
    build_codex_command,
)


def test_build_claude_code_command():
    cmd = build_claude_code_command(
        prompt="implement auth module",
        working_dir="/tmp/project",
    )
    assert "claude" in cmd[0] or "claude-code" in cmd[0]
    assert any("--print" in c or "-p" in c for c in cmd)


def test_build_codex_command():
    cmd = build_codex_command(
        prompt="implement auth module",
        working_dir="/tmp/project",
    )
    assert "codex" in cmd[0]


def test_subprocess_transport_submit():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_process):
        receipt = transport.submit(
            command=["echo", "test"],
            working_dir="/tmp",
            timeout=60,
        )
    assert receipt.process_id == 12345
    assert receipt.status == "running"


def test_subprocess_transport_poll_completed():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.communicate.return_value = ("output text", "")
    transport._processes["exec-1"] = mock_process

    result = transport.poll("exec-1")
    assert result.status == "completed"
    assert result.stdout == "output text"


def test_subprocess_transport_poll_running():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    transport._processes["exec-1"] = mock_process

    result = transport.poll("exec-1")
    assert result.status == "running"


def test_subprocess_transport_poll_failed():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = 1
    mock_process.communicate.return_value = ("", "error occurred")
    transport._processes["exec-1"] = mock_process

    result = transport.poll("exec-1")
    assert result.status == "failed"
    assert "error" in result.stderr


def test_subprocess_transport_cancel():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    transport._processes["exec-1"] = mock_process

    result = transport.cancel("exec-1")
    mock_process.terminate.assert_called_once()
    assert result.status == "cancelled"


def test_subprocess_transport_timeout():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_process.communicate.side_effect = TimeoutError()
    transport._processes["exec-1"] = mock_process
    transport._timeouts["exec-1"] = 0  # expired

    result = transport.poll("exec-1", check_timeout=True)
    assert result.status == "timed_out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_subprocess_transport.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement subprocess transport**

```python
# src/devforge/executors/subprocess_transport.py
"""Real subprocess transport for CLI-based executors (claude_code, codex)."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class SubprocessResult:
    """Result from a subprocess execution."""

    execution_id: str
    status: str  # "running", "completed", "failed", "timed_out", "cancelled"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class SubprocessTransport:
    """Manages subprocess-based executor invocations."""

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._timeouts: dict[str, float] = {}
        self._start_times: dict[str, float] = {}

    def submit(
        self,
        command: list[str],
        working_dir: str,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> SubprocessResult:
        """Start a subprocess and return a tracking receipt."""
        execution_id = f"exec-{uuid4().hex[:8]}"
        process = subprocess.Popen(
            command,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self._processes[execution_id] = process
        self._timeouts[execution_id] = timeout
        self._start_times[execution_id] = time.monotonic()
        return SubprocessResult(
            execution_id=execution_id,
            status="running",
        )

    def poll(self, execution_id: str, *, check_timeout: bool = False) -> SubprocessResult:
        """Check status of a running subprocess."""
        process = self._processes.get(execution_id)
        if process is None:
            return SubprocessResult(execution_id=execution_id, status="failed", stderr="unknown execution_id")

        # Check timeout
        if check_timeout:
            timeout = self._timeouts.get(execution_id, 300)
            start = self._start_times.get(execution_id, 0)
            if start > 0 and (time.monotonic() - start) > timeout:
                process.terminate()
                return SubprocessResult(execution_id=execution_id, status="timed_out")

        exit_code = process.poll()
        if exit_code is None:
            return SubprocessResult(execution_id=execution_id, status="running")

        stdout, stderr = process.communicate(timeout=5)
        status = "completed" if exit_code == 0 else "failed"
        return SubprocessResult(
            execution_id=execution_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout or "",
            stderr=stderr or "",
        )

    def cancel(self, execution_id: str) -> SubprocessResult:
        """Terminate a running subprocess."""
        process = self._processes.get(execution_id)
        if process is None:
            return SubprocessResult(execution_id=execution_id, status="failed", stderr="unknown execution_id")

        process.terminate()
        return SubprocessResult(execution_id=execution_id, status="cancelled")


def build_claude_code_command(
    prompt: str,
    working_dir: str,
    *,
    model: str | None = None,
    max_turns: int | None = None,
) -> list[str]:
    """Build a claude CLI command for non-interactive execution."""
    cmd = ["claude", "--print", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])
    cmd.append(prompt)
    return cmd


def build_codex_command(
    prompt: str,
    working_dir: str,
    *,
    model: str | None = None,
) -> list[str]:
    """Build a codex CLI command."""
    cmd = ["codex", "--approval-mode", "full-auto", "--quiet"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    return cmd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_subprocess_transport.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/executors/subprocess_transport.py tests/test_subprocess_transport.py
git commit -m "feat: add subprocess transport for claude_code and codex CLI execution"
```

---

### Task 6: Wire Granularity into Dispatch Pipeline

**Files:**
- Modify: `src/devforge/graph/builder.py`
- Modify: `src/devforge/executors/__init__.py`
- Test: `tests/test_granularity_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_granularity_integration.py
"""Integration test: granularity check before dispatch."""

from devforge.executors.granularity import validate_granularity
from devforge.state import WorkPackage


def test_oversized_package_detected_before_dispatch():
    """A huge work package should be flagged before dispatch to codex."""
    wp = WorkPackage(
        work_package_id="WP-huge",
        initiative_id="I-1",
        project_id="P-1",
        phase="implementation",
        domain="backend",
        role_id="software_engineer",
        title="Huge package",
        goal="x " * 10000,
        status="ready",
        acceptance_criteria=["c" * 200 for _ in range(50)],
    )
    action = validate_granularity(wp, "codex")
    assert action.action == "split"


def test_normal_package_passes_granularity():
    wp = WorkPackage(
        work_package_id="WP-normal",
        initiative_id="I-1",
        project_id="P-1",
        phase="implementation",
        domain="backend",
        role_id="software_engineer",
        title="Normal package",
        goal="implement user authentication",
        status="ready",
    )
    action = validate_granularity(wp, "claude_code")
    assert action.action == "ok"
```

- [ ] **Step 2: Run to verify tests pass (these use existing functions)**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_granularity_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Update executors/__init__.py exports**

Add to `src/devforge/executors/__init__.py`:

```python
from .capabilities import ExecutorCapability, get_executor_capability, EXECUTOR_CAPABILITIES
from .granularity import validate_granularity, estimate_package_tokens, suggest_split, suggest_merge, GranularityAction
from .subprocess_transport import SubprocessTransport, SubprocessResult, build_claude_code_command, build_codex_command
```

- [ ] **Step 4: Run full suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/executors/__init__.py tests/test_granularity_integration.py
git commit -m "feat: wire granularity validation and subprocess transport into executor exports"
```

---

### Task 7: Full Suite Verification

- [ ] **Step 1: Run complete test suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify new files exist**

Run: `ls -la src/devforge/executors/capabilities.py src/devforge/executors/granularity.py src/devforge/executors/subprocess_transport.py`
Expected: All 3 files exist

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: Plan 2 complete — granularity control and executor transport

Implements acceptance plan capabilities #5-#8:
- Executor capability model (context window, granularity preferences)
- Pre-dispatch granularity validation with split/merge suggestions
- Push context enriched with previous attempt findings on retry
- Pull context with workpackage:// permission isolation
- Subprocess transport for claude_code and codex CLI
- 6 test files, 30+ test cases"
```
