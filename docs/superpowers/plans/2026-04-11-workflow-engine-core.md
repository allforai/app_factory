# Workflow Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone workflow engine that reads `.devforge/workflows/`, executes nodes via Codex/Claude, tracks artifacts and transitions, and exposes `wf` commands in the REPL — replacing meta-skill's `/run` without touching the existing run_cycle machinery.

**Architecture:** New `src/devforge/workflow/` module (models, artifacts, store, validation, engine) with token-efficient file splitting (index/manifest/node/transitions separate files). REPL gets new `wf` intent kinds and handlers. Engine calls executors via subprocess, consistent with how `run_executor_doctor` calls Codex. Two-layer status model: `WorkflowPhase` (engine-internal, in manifest) vs `WorkflowStatus` (user-visible, in index). Human-in-the-loop planning: planner node runs first, user confirms y/n, then fully automatic execution.

**Tech Stack:** Python 3.12, TypedDict, pathlib, subprocess, jsonlines (append-only transitions), uv, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/devforge/workflow/__init__.py` | Create | Export `WorkflowEngine`, `run_one_cycle` |
| `src/devforge/workflow/models.py` | Create | All TypedDict/Literal definitions |
| `src/devforge/workflow/artifacts.py` | Create | exit_artifacts existence + size checking |
| `src/devforge/workflow/store.py` | Create | Read/write index, manifest, node, transitions (atomic writes) |
| `src/devforge/workflow/validation.py` | Create | Workflow node graph validation |
| `src/devforge/workflow/engine.py` | Create | select_next_nodes, reconcile, run_one_cycle |
| `src/devforge/session.py` | Modify | Add wf IntentKind values |
| `src/devforge/repl.py` | Modify | wf command parsing, rendering, handlers, startup |
| `tests/test_workflow_models.py` | Create | TypedDict shape verification |
| `tests/test_workflow_artifacts.py` | Create | Artifact checking unit tests |
| `tests/test_workflow_store.py` | Create | Store read/write round-trip tests |
| `tests/test_workflow_validation.py` | Create | Validation error cases |
| `tests/test_workflow_engine.py` | Create | select_next_nodes, reconcile, run_one_cycle (mocked dispatch) |

---

### Task 1: `models.py` and `__init__.py`

**Files:**
- Create: `src/devforge/workflow/__init__.py`
- Create: `src/devforge/workflow/models.py`
- Create: `tests/test_workflow_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_models.py
from devforge.workflow.models import (
    NodeManifestEntry,
    NodeDefinition,
    WorkflowManifest,
    WorkflowIndex,
    WorkflowIndexEntry,
    TransitionEntry,
    PlannerOutput,
    NodeStatus,
    WorkflowStatus,
    WorkflowPhase,
)


def test_node_manifest_entry_is_dict() -> None:
    entry: NodeManifestEntry = {
        "id": "discover",
        "status": "pending",
        "depends_on": [],
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "executor": "codex",
        "mode": None,
        "parent_node_id": None,
        "depth": 0,
        "attempt_count": 0,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
    }
    assert isinstance(entry, dict)
    assert entry["status"] == "pending"
    assert entry["attempt_count"] == 0
    assert entry["mode"] is None


def test_node_definition_is_dict() -> None:
    node: NodeDefinition = {
        "id": "discover",
        "capability": "discovery",
        "goal": "Scan the repo",
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "knowledge_refs": ["src/devforge/knowledge/content/capabilities/discovery.md"],
        "executor": "codex",
        "mode": None,
    }
    assert node["capability"] == "discovery"
    assert node["mode"] is None


def test_workflow_manifest_has_workflow_status() -> None:
    manifest: WorkflowManifest = {
        "id": "wf-test-001",
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": "running",
        "nodes": [],
    }
    assert manifest["workflow_status"] == "running"
    assert manifest["nodes"] == []


def test_workflow_index_is_dict() -> None:
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": "wf-test-001",
        "workflows": [],
    }
    assert index["schema_version"] == "1.0"


def test_planner_output_is_dict() -> None:
    output: PlannerOutput = {
        "nodes": [],
        "summary": "計劃包含 0 個節點",
    }
    assert output["summary"] == "計劃包含 0 個節點"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_models.py -v
```

Expected: `ImportError: No module named 'devforge.workflow'`

- [ ] **Step 3: Create `src/devforge/workflow/models.py`**

```python
"""TypedDict definitions for the DevForge workflow engine."""

from __future__ import annotations

from typing import Literal, TypedDict

NodeStatus = Literal["pending", "running", "completed", "failed"]

# Engine-internal phase (stored in manifest.workflow_status)
WorkflowPhase = Literal["planning", "awaiting_confirm", "running", "complete", "failed"]

# User-visible lifecycle status (stored in index.json per workflow)
WorkflowStatus = Literal["active", "complete", "paused", "failed"]


class NodeManifestEntry(TypedDict):
    id: str
    status: NodeStatus
    depends_on: list[str]
    exit_artifacts: list[str]
    executor: str
    mode: str | None          # None = regular node, "planning" = planner node
    parent_node_id: str | None
    depth: int
    attempt_count: int        # cumulative execution attempts
    last_started_at: str | None
    last_completed_at: str | None
    last_error: str | None


class NodeDefinition(TypedDict):
    id: str
    capability: str
    goal: str
    exit_artifacts: list[str]
    knowledge_refs: list[str]
    executor: str
    mode: str | None          # None | "planning"


class WorkflowManifest(TypedDict):
    id: str
    goal: str
    created_at: str
    workflow_status: WorkflowPhase   # engine-internal phase
    nodes: list[NodeManifestEntry]


class WorkflowIndexEntry(TypedDict):
    id: str
    goal: str
    status: WorkflowStatus
    created_at: str


class WorkflowIndex(TypedDict):
    schema_version: str
    active_workflow_id: str | None
    workflows: list[WorkflowIndexEntry]


class TransitionEntry(TypedDict):
    node: str
    status: Literal["completed", "failed"]
    started_at: str
    completed_at: str
    artifacts_created: list[str]
    error: str | None


class PlannerOutput(TypedDict):
    nodes: list[NodeDefinition]
    summary: str
```

- [ ] **Step 4: Create `src/devforge/workflow/__init__.py`**

```python
"""DevForge workflow engine."""

from devforge.workflow.engine import run_one_cycle
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    NodeStatus,
    PlannerOutput,
    TransitionEntry,
    WorkflowIndex,
    WorkflowIndexEntry,
    WorkflowManifest,
    WorkflowPhase,
    WorkflowStatus,
)

__all__ = [
    "run_one_cycle",
    "NodeDefinition",
    "NodeManifestEntry",
    "NodeStatus",
    "PlannerOutput",
    "TransitionEntry",
    "WorkflowIndex",
    "WorkflowIndexEntry",
    "WorkflowManifest",
    "WorkflowPhase",
    "WorkflowStatus",
]
```

- [ ] **Step 5: Run the test**

```bash
uv run python -m pytest tests/test_workflow_models.py -v
```

Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add src/devforge/workflow/__init__.py src/devforge/workflow/models.py tests/test_workflow_models.py
git commit -m "feat: add workflow engine TypedDict models"
```

---

### Task 2: `artifacts.py`

**Files:**
- Create: `src/devforge/workflow/artifacts.py`
- Create: `tests/test_workflow_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_artifacts.py
from pathlib import Path
from devforge.workflow.artifacts import check_artifacts


def test_check_artifacts_all_present(tmp_path: Path) -> None:
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    f1.write_text("{}")
    f2.write_text("{}")
    assert check_artifacts(tmp_path, ["a.json", "b.json"]) is True


def test_check_artifacts_one_missing(tmp_path: Path) -> None:
    f1 = tmp_path / "a.json"
    f1.write_text("{}")
    assert check_artifacts(tmp_path, ["a.json", "missing.json"]) is False


def test_check_artifacts_empty_list(tmp_path: Path) -> None:
    assert check_artifacts(tmp_path, []) is True


def test_check_artifacts_nested_path(tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "deep.json"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}")
    assert check_artifacts(tmp_path, ["sub/deep.json"]) is True


def test_check_artifacts_empty_file_returns_false(tmp_path: Path) -> None:
    f = tmp_path / "empty.json"
    f.write_text("")
    assert check_artifacts(tmp_path, ["empty.json"]) is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_artifacts.py -v
```

Expected: `ImportError: cannot import name 'check_artifacts'`

- [ ] **Step 3: Create `src/devforge/workflow/artifacts.py`**

```python
"""exit_artifacts existence and size checking for the workflow engine."""

from __future__ import annotations

from pathlib import Path


def check_artifacts(root: Path, paths: list[str]) -> bool:
    """Return True iff every path in paths exists relative to root and has size > 0."""
    return all(
        (root / p).exists() and (root / p).stat().st_size > 0
        for p in paths
    )
```

- [ ] **Step 4: Run the test**

```bash
uv run python -m pytest tests/test_workflow_artifacts.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/artifacts.py tests/test_workflow_artifacts.py
git commit -m "feat: add workflow artifact existence and size checker"
```

---

### Task 3: `store.py`

**Files:**
- Create: `src/devforge/workflow/store.py`
- Create: `tests/test_workflow_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_store.py
import json
from pathlib import Path
from devforge.workflow.models import (
    WorkflowIndex,
    WorkflowManifest,
    NodeDefinition,
    TransitionEntry,
)
from devforge.workflow.store import (
    read_index,
    write_index,
    read_manifest,
    write_manifest,
    read_node,
    write_node,
    append_transition,
    read_transitions,
    active_workflow_id,
)


def _make_index(wf_id: str = "wf-test-001") -> WorkflowIndex:
    return {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [
            {"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}
        ],
    }


def _make_manifest(wf_id: str = "wf-test-001") -> WorkflowManifest:
    return {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": "running",
        "nodes": [
            {
                "id": "discover",
                "status": "pending",
                "depends_on": [],
                "exit_artifacts": [".devforge/artifacts/summary.json"],
                "executor": "codex",
                "mode": None,
                "parent_node_id": None,
                "depth": 0,
                "attempt_count": 0,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
            }
        ],
    }


def test_index_round_trip(tmp_path: Path) -> None:
    index = _make_index()
    write_index(tmp_path, index)
    assert read_index(tmp_path) == index


def test_read_index_returns_empty_when_missing(tmp_path: Path) -> None:
    result = read_index(tmp_path)
    assert result["schema_version"] == "1.0"
    assert result["active_workflow_id"] is None
    assert result["workflows"] == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = _make_manifest()
    write_manifest(tmp_path, "wf-test-001", manifest)
    assert read_manifest(tmp_path, "wf-test-001") == manifest


def test_node_round_trip(tmp_path: Path) -> None:
    node: NodeDefinition = {
        "id": "discover",
        "capability": "discovery",
        "goal": "Scan the repo",
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": None,
    }
    write_node(tmp_path, "wf-test-001", node)
    assert read_node(tmp_path, "wf-test-001", "discover") == node


def test_append_transition_creates_jsonl(tmp_path: Path) -> None:
    entry: TransitionEntry = {
        "node": "discover",
        "status": "completed",
        "started_at": "2026-04-11T00:00:00Z",
        "completed_at": "2026-04-11T00:01:00Z",
        "artifacts_created": [".devforge/artifacts/summary.json"],
        "error": None,
    }
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    append_transition(tmp_path, "wf-test-001", entry)
    append_transition(tmp_path, "wf-test-001", entry)
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 2
    assert transitions[0]["node"] == "discover"


def test_read_transitions_skips_corrupted_lines(tmp_path: Path) -> None:
    write_manifest(tmp_path, "wf-test-001", _make_manifest())
    # Write one valid + one corrupted line directly
    transitions_path = tmp_path / ".devforge" / "workflows" / "wf-test-001" / "transitions.jsonl"
    transitions_path.parent.mkdir(parents=True, exist_ok=True)
    transitions_path.write_text(
        '{"node": "a", "status": "completed", "started_at": "t", "completed_at": "t", "artifacts_created": [], "error": null}\n'
        'NOT VALID JSON {{{\n',
        encoding="utf-8",
    )
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 1
    assert transitions[0]["node"] == "a"


def test_write_index_is_atomic(tmp_path: Path) -> None:
    # write_index should not leave partial files; verify the file is complete after write
    index = _make_index()
    write_index(tmp_path, index)
    index_path = tmp_path / ".devforge" / "workflows" / "index.json"
    content = json.loads(index_path.read_text())
    assert content["schema_version"] == "1.0"


def test_active_workflow_id_returns_none_when_missing(tmp_path: Path) -> None:
    assert active_workflow_id(tmp_path) is None


def test_active_workflow_id_returns_value(tmp_path: Path) -> None:
    write_index(tmp_path, _make_index("wf-abc"))
    assert active_workflow_id(tmp_path) == "wf-abc"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_store.py -v
```

Expected: `ImportError: cannot import name 'read_index' from 'devforge.workflow.store'`

- [ ] **Step 3: Create `src/devforge/workflow/store.py`**

```python
"""File I/O layer for the workflow engine.

Directory layout:
  <root>/.devforge/workflows/
    index.json
    <wf-id>/
      manifest.json
      nodes/<node-id>.json
      transitions.jsonl

Atomicity: manifest.json and index.json use temp-file + os.replace().
transitions.jsonl is append-only; corrupted lines are skipped on read.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from devforge.workflow.models import (
    NodeDefinition,
    TransitionEntry,
    WorkflowIndex,
    WorkflowManifest,
)

_WORKFLOWS_DIR = ".devforge/workflows"
_INDEX_FILE = "index.json"
_MANIFEST_FILE = "manifest.json"
_TRANSITIONS_FILE = "transitions.jsonl"
_EMPTY_INDEX: WorkflowIndex = {
    "schema_version": "1.0",
    "active_workflow_id": None,
    "workflows": [],
}


def _workflows_root(root: Path) -> Path:
    return root / _WORKFLOWS_DIR


def _wf_dir(root: Path, wf_id: str) -> Path:
    return _workflows_root(root) / wf_id


def _index_path(root: Path) -> Path:
    return _workflows_root(root) / _INDEX_FILE


def _manifest_path(root: Path, wf_id: str) -> Path:
    return _wf_dir(root, wf_id) / _MANIFEST_FILE


def _node_path(root: Path, wf_id: str, node_id: str) -> Path:
    return _wf_dir(root, wf_id) / "nodes" / f"{node_id}.json"


def _transitions_path(root: Path, wf_id: str) -> Path:
    return _wf_dir(root, wf_id) / _TRANSITIONS_FILE


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_index(root: Path) -> WorkflowIndex:
    path = _index_path(root)
    if not path.exists():
        return dict(_EMPTY_INDEX)  # type: ignore[return-value]
    return json.loads(path.read_text(encoding="utf-8"))


def write_index(root: Path, index: WorkflowIndex) -> None:
    _atomic_write(
        _index_path(root),
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
    )


def read_manifest(root: Path, wf_id: str) -> WorkflowManifest:
    path = _manifest_path(root, wf_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(root: Path, wf_id: str, manifest: WorkflowManifest) -> None:
    _atomic_write(
        _manifest_path(root, wf_id),
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )


def read_node(root: Path, wf_id: str, node_id: str) -> NodeDefinition:
    path = _node_path(root, wf_id, node_id)
    if not path.exists():
        raise FileNotFoundError(f"Node definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_node(root: Path, wf_id: str, node: NodeDefinition) -> None:
    path = _node_path(root, wf_id, node["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(node, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_transition(root: Path, wf_id: str, entry: TransitionEntry) -> None:
    path = _transitions_path(root, wf_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_transitions(root: Path, wf_id: str) -> list[TransitionEntry]:
    path = _transitions_path(root, wf_id)
    if not path.exists():
        return []
    result: list[TransitionEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # skip corrupted lines
    return result


def active_workflow_id(root: Path) -> str | None:
    return read_index(root)["active_workflow_id"]
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_workflow_store.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/store.py tests/test_workflow_store.py
git commit -m "feat: add workflow store file I/O layer with atomic writes"
```

---

### Task 4: `validation.py`

**Files:**
- Create: `src/devforge/workflow/validation.py`
- Create: `tests/test_workflow_validation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_validation.py
import pytest
from devforge.workflow.models import NodeDefinition
from devforge.workflow.validation import validate_workflow


def _node(
    node_id: str,
    depends_on: list[str] | None = None,
    executor: str = "codex",
    mode: str | None = None,
) -> NodeDefinition:
    return {
        "id": node_id,
        "capability": "discovery",
        "goal": f"Run {node_id}",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": executor,
        "mode": mode,
    }


def test_valid_linear_graph_passes() -> None:
    nodes = [_node("a"), _node("b", depends_on=["a"]), _node("c", depends_on=["b"])]
    validate_workflow(nodes)  # no exception


def test_duplicate_ids_raise() -> None:
    nodes = [_node("a"), _node("a")]
    with pytest.raises(ValueError, match="duplicate"):
        validate_workflow(nodes)


def test_missing_dependency_raises() -> None:
    nodes = [_node("b", depends_on=["nonexistent"])]
    with pytest.raises(ValueError, match="nonexistent"):
        validate_workflow(nodes)


def test_self_dependency_raises() -> None:
    nodes = [_node("a", depends_on=["a"])]
    with pytest.raises(ValueError, match="self"):
        validate_workflow(nodes)


def test_cyclic_dependency_raises() -> None:
    nodes = [_node("a", depends_on=["b"]), _node("b", depends_on=["a"])]
    with pytest.raises(ValueError, match="cycl"):
        validate_workflow(nodes)


def test_invalid_executor_raises() -> None:
    nodes = [_node("a", executor="invalid_executor")]
    with pytest.raises(ValueError, match="executor"):
        validate_workflow(nodes)


def test_empty_graph_passes() -> None:
    validate_workflow([])  # no exception
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_validation.py -v
```

Expected: `ImportError: cannot import name 'validate_workflow'`

- [ ] **Step 3: Create `src/devforge/workflow/validation.py`**

```python
"""Workflow node graph validation.

Called by wf init (before writing files) and by the planner flow (before
accepting planner output). Raises ValueError describing the first violation found.

knowledge_refs pointing to missing files are warnings only (stderr), not errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

from devforge.workflow.models import NodeDefinition

_VALID_EXECUTORS = {"codex", "claude_code"}


def validate_workflow(nodes: list[NodeDefinition], root: Path | None = None) -> None:
    """Validate node graph. Raises ValueError on the first structural violation.

    Args:
        nodes: list of NodeDefinition to validate.
        root: project root for knowledge_refs existence check (optional; warnings only).
    """
    ids = [n["id"] for n in nodes]

    # Unique IDs
    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            raise ValueError(f"duplicate node id: '{node_id}'")
        seen.add(node_id)

    id_set = set(ids)
    for node in nodes:
        node_id = node["id"]

        # Self-dependency
        if node_id in node.get("depends_on", []):
            raise ValueError(f"node '{node_id}' has self-dependency")

        # Missing dependencies
        for dep in node.get("depends_on", []):
            if dep not in id_set:
                raise ValueError(
                    f"node '{node_id}' depends on '{dep}' which does not exist in the workflow"
                )

        # Valid executor
        if node.get("executor", "codex") not in _VALID_EXECUTORS:
            raise ValueError(
                f"node '{node_id}' has invalid executor '{node['executor']}' "
                f"(must be one of: {sorted(_VALID_EXECUTORS)})"
            )

        # knowledge_refs: warn only
        if root is not None:
            for ref in node.get("knowledge_refs", []):
                if not (root / ref).exists():
                    print(
                        f"WARNING: knowledge_ref '{ref}' for node '{node_id}' not found — skipping",
                        file=sys.stderr,
                    )

    # Cycle detection (DFS)
    adj: dict[str, list[str]] = {n["id"]: list(n.get("depends_on", [])) for n in nodes}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node_id: str) -> None:
        visited.add(node_id)
        in_stack.add(node_id)
        for dep in adj.get(node_id, []):
            if dep not in visited:
                dfs(dep)
            elif dep in in_stack:
                raise ValueError(f"cyclic dependency detected involving node '{dep}'")
        in_stack.discard(node_id)

    for node_id in ids:
        if node_id not in visited:
            dfs(node_id)
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_workflow_validation.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
uv run python -m pytest -q
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add src/devforge/workflow/validation.py tests/test_workflow_validation.py
git commit -m "feat: add workflow graph validation (cycles, duplicates, missing deps)"
```

---

### Task 5: `engine.py` — node selection and artifact reconciliation

**Files:**
- Create: `src/devforge/workflow/engine.py`
- Create: `tests/test_workflow_engine.py` (selection + reconcile tests only)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_engine.py
from pathlib import Path
from devforge.workflow.models import NodeManifestEntry, WorkflowManifest
from devforge.workflow.engine import select_next_nodes, reconcile_artifacts


def _node(
    node_id: str,
    status: str = "pending",
    depends_on: list[str] | None = None,
    exit_artifacts: list[str] | None = None,
    mode: str | None = None,
    attempt_count: int = 0,
) -> NodeManifestEntry:
    return {
        "id": node_id,
        "status": status,  # type: ignore[typeddict-item]
        "depends_on": depends_on or [],
        "exit_artifacts": exit_artifacts or [],
        "executor": "codex",
        "mode": mode,
        "parent_node_id": None,
        "depth": 0,
        "attempt_count": attempt_count,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
    }


def _manifest(nodes: list[NodeManifestEntry], phase: str = "running") -> WorkflowManifest:
    return {
        "id": "wf-test",
        "goal": "test",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": phase,  # type: ignore[typeddict-item]
        "nodes": nodes,
    }


def test_select_next_nodes_no_deps() -> None:
    manifest = _manifest([_node("a"), _node("b")])
    result = select_next_nodes(manifest)
    assert {n["id"] for n in result} == {"a", "b"}


def test_select_next_nodes_respects_deps() -> None:
    manifest = _manifest([_node("a"), _node("b", depends_on=["a"])])
    result = select_next_nodes(manifest)
    assert [n["id"] for n in result] == ["a"]


def test_select_next_nodes_dep_completed() -> None:
    manifest = _manifest([_node("a", status="completed"), _node("b", depends_on=["a"])])
    result = select_next_nodes(manifest)
    assert [n["id"] for n in result] == ["b"]


def test_select_next_nodes_max_concurrent() -> None:
    nodes = [_node(f"n{i}") for i in range(5)]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert len(result) == 3  # MAX_CONCURRENT = 3


def test_select_next_nodes_running_counts_toward_limit() -> None:
    nodes = [_node("a", status="running"), _node("b"), _node("c"), _node("d")]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert len(result) == 2  # 1 running + 2 new = 3 total


def test_select_next_nodes_empty_when_all_running() -> None:
    nodes = [_node(f"n{i}", status="running") for i in range(3)]
    manifest = _manifest(nodes)
    result = select_next_nodes(manifest)
    assert result == []


def test_reconcile_artifacts_marks_completed(tmp_path: Path) -> None:
    artifact = tmp_path / "summary.json"
    artifact.write_text("{}")
    nodes = [_node("discover", exit_artifacts=["summary.json"])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "completed"


def test_reconcile_artifacts_leaves_pending_when_missing(tmp_path: Path) -> None:
    nodes = [_node("discover", exit_artifacts=["missing.json"])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


def test_reconcile_artifacts_no_artifacts_stays_pending(tmp_path: Path) -> None:
    nodes = [_node("discover", exit_artifacts=[])]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"


def test_reconcile_skips_planning_nodes(tmp_path: Path) -> None:
    # Planning nodes never reconcile via artifacts even if files exist
    artifact = tmp_path / "plan.json"
    artifact.write_text("{}")
    nodes = [_node("planner", exit_artifacts=["plan.json"], mode="planning")]
    manifest = _manifest(nodes)
    updated = reconcile_artifacts(tmp_path, manifest)
    assert updated["nodes"][0]["status"] == "pending"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_engine.py -v
```

Expected: `ImportError: cannot import name 'select_next_nodes' from 'devforge.workflow.engine'`

- [ ] **Step 3: Create `src/devforge/workflow/engine.py`** (selection + reconcile only)

```python
"""Workflow engine: node selection, artifact reconciliation, and execution."""

from __future__ import annotations

import copy
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devforge.workflow.artifacts import check_artifacts
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    TransitionEntry,
    WorkflowManifest,
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

MAX_CONCURRENT = 3


def select_next_nodes(manifest: WorkflowManifest) -> list[NodeManifestEntry]:
    """Return nodes that are ready to run (pending + deps met + under concurrency limit)."""
    completed_ids = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running_count = sum(1 for n in manifest["nodes"] if n["status"] == "running")
    slots = MAX_CONCURRENT - running_count
    if slots <= 0:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] == "pending"
        and set(n.get("depends_on", [])) <= completed_ids
    ][:slots]


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk.

    Planning nodes (mode == "planning") are never reconciled via artifacts.
    Nodes with empty exit_artifacts are not automatically completed.
    """
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node.get("mode") == "planning":
            continue
        if node["status"] in ("pending", "running") and node["exit_artifacts"]:
            if check_artifacts(root, node["exit_artifacts"]):
                node["status"] = "completed"
                node["last_error"] = None
    return updated


def run_one_cycle(root: Path) -> dict[str, Any]:
    """Execute one workflow cycle: reconcile → select → dispatch → persist."""
    ...  # implemented in Task 6
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_workflow_engine.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/engine.py tests/test_workflow_engine.py
git commit -m "feat: add workflow node selection and artifact reconciliation"
```

---

### Task 6: `engine.py` — `run_one_cycle` with executor dispatch

**Files:**
- Modify: `src/devforge/workflow/engine.py`
- Modify: `tests/test_workflow_engine.py`

- [ ] **Step 1: Write the failing tests** (append to existing test file)

```python
# append to tests/test_workflow_engine.py

from unittest.mock import patch
from devforge.workflow.store import write_index, write_manifest, write_node
from devforge.workflow.models import WorkflowIndex
from devforge.workflow.engine import run_one_cycle


def _setup_workflow(
    tmp_path: Path,
    nodes_status: dict[str, str] | None = None,
    phase: str = "running",
    attempt_counts: dict[str, int] | None = None,
) -> None:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)

    nodes_status = nodes_status or {"discover": "pending"}
    attempt_counts = attempt_counts or {}
    manifest_nodes: list[NodeManifestEntry] = []
    for node_id, status in nodes_status.items():
        manifest_nodes.append(_node(
            node_id,
            status=status,
            attempt_count=attempt_counts.get(node_id, 0),
        ))
    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "workflow_status": phase,  # type: ignore[typeddict-item]
        "nodes": manifest_nodes,
    }
    write_manifest(tmp_path, wf_id, manifest)

    for node_id in nodes_status:
        node_def: NodeDefinition = {
            "id": node_id,
            "capability": "discovery",
            "goal": f"Run {node_id}",
            "exit_artifacts": [],
            "knowledge_refs": [],
            "executor": "codex",
            "mode": None,
        }
        write_node(tmp_path, wf_id, node_def)


def test_run_one_cycle_dispatches_pending_node(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        result = run_one_cycle(tmp_path)
    assert result["dispatched"] == ["discover"]
    mock_dispatch.assert_called_once()


def test_run_one_cycle_marks_node_completed_on_success(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "completed"
    assert node["attempt_count"] == 1
    assert node["last_completed_at"] is not None
    assert node["last_error"] is None


def test_run_one_cycle_marks_node_failed_on_error(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 1, "output": "error msg", "executor": "codex"}
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert node["last_error"] == "error msg"
    assert node["attempt_count"] == 1


def test_run_one_cycle_writes_transition_log(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 0, "output": "ok", "executor": "codex"}
        run_one_cycle(tmp_path)
    from devforge.workflow.store import read_transitions
    transitions = read_transitions(tmp_path, "wf-test-001")
    assert len(transitions) == 1
    assert transitions[0]["node"] == "discover"
    assert transitions[0]["status"] == "completed"


def test_run_one_cycle_returns_all_complete_when_done(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, {"discover": "completed"})
    result = run_one_cycle(tmp_path)
    assert result["status"] == "all_complete"
    assert result["dispatched"] == []
    # index.status should be synced to "complete"
    index = read_index(tmp_path)
    assert index["workflows"][0]["status"] == "complete"


def test_run_one_cycle_returns_no_active_workflow_when_missing(tmp_path: Path) -> None:
    result = run_one_cycle(tmp_path)
    assert result["status"] == "no_active_workflow"


def test_run_one_cycle_returns_manifest_missing(tmp_path: Path) -> None:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)
    # manifest file is NOT written
    result = run_one_cycle(tmp_path)
    assert result["status"] == "manifest_missing"


def test_run_one_cycle_returns_awaiting_confirm(tmp_path: Path) -> None:
    _setup_workflow(tmp_path, phase="awaiting_confirm")
    result = run_one_cycle(tmp_path)
    assert result["status"] == "awaiting_confirm"


def test_run_one_cycle_executor_not_found(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.side_effect = FileNotFoundError("codex not found")
        run_one_cycle(tmp_path)
    manifest = read_manifest(tmp_path, "wf-test-001")
    node = manifest["nodes"][0]
    assert node["status"] == "failed"
    assert "executor not found" in (node["last_error"] or "")


def test_run_one_cycle_workflow_fails_after_max_attempts(tmp_path: Path) -> None:
    # attempt_count already at 2, so this attempt makes it 3 → workflow_status = failed
    _setup_workflow(tmp_path, attempt_counts={"discover": 2})
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 1, "output": "still failing", "executor": "codex"}
        result = run_one_cycle(tmp_path)
    assert result["status"] == "workflow_failed"
    manifest = read_manifest(tmp_path, "wf-test-001")
    assert manifest["workflow_status"] == "failed"
    index = read_index(tmp_path)
    assert index["workflows"][0]["status"] == "failed"
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run python -m pytest tests/test_workflow_engine.py::test_run_one_cycle_dispatches_pending_node -v
```

Expected: `FAILED` — `run_one_cycle` returns `None` (stub)

- [ ] **Step 3: Implement `_dispatch_node` and `run_one_cycle` in `engine.py`**

Replace the stub `run_one_cycle` and add helpers. Replace the entire file content with:

```python
"""Workflow engine: node selection, artifact reconciliation, and execution."""

from __future__ import annotations

import copy
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devforge.workflow.artifacts import check_artifacts
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    TransitionEntry,
    WorkflowManifest,
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

MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3


def select_next_nodes(manifest: WorkflowManifest) -> list[NodeManifestEntry]:
    """Return nodes that are ready to run (pending + deps met + under concurrency limit)."""
    completed_ids = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running_count = sum(1 for n in manifest["nodes"] if n["status"] == "running")
    slots = MAX_CONCURRENT - running_count
    if slots <= 0:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] == "pending"
        and set(n.get("depends_on", [])) <= completed_ids
    ][:slots]


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk.

    Planning nodes (mode == "planning") are never reconciled via artifacts.
    Nodes with empty exit_artifacts are not automatically completed.
    """
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node.get("mode") == "planning":
            continue
        if node["status"] in ("pending", "running") and node["exit_artifacts"]:
            if check_artifacts(root, node["exit_artifacts"]):
                node["status"] = "completed"
                node["last_error"] = None
    return updated


def _load_knowledge(refs: list[str], root: Path) -> str:
    """Read knowledge_refs files and join their content. Missing files are skipped."""
    parts: list[str] = []
    for ref in refs:
        path = root / ref
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def _dispatch_node(node: NodeDefinition, root: Path) -> dict[str, Any]:
    """Call executor subprocess with node goal + knowledge content."""
    knowledge = _load_knowledge(node.get("knowledge_refs", []), root)
    prompt = node["goal"]
    if knowledge:
        prompt = f"{prompt}\n\n{knowledge}"
    executor = node.get("executor", "codex")
    if executor == "codex":
        cmd = ["codex", "exec", "--full-auto", "--cd", str(root), prompt]
    else:
        cmd = ["claude", "--print", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or proc.stderr or "").strip(),
        "executor": executor,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_index_status(root: Path, wf_id: str, status: str) -> None:
    """Update the index entry status for a workflow."""
    index = read_index(root)
    for entry in index["workflows"]:
        if entry["id"] == wf_id:
            entry["status"] = status  # type: ignore[typeddict-item]
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

    # Human-in-the-loop gate: planner ran, waiting for user confirmation
    if manifest["workflow_status"] == "awaiting_confirm":
        return {"status": "awaiting_confirm", "dispatched": []}

    manifest = reconcile_artifacts(root, manifest)

    all_done = all(n["status"] == "completed" for n in manifest["nodes"])
    if all_done and manifest["nodes"]:
        manifest["workflow_status"] = "complete"
        write_manifest(root, wf_id, manifest)
        _sync_index_status(root, wf_id, "complete")
        return {"status": "all_complete", "dispatched": []}

    candidates = select_next_nodes(manifest)
    if not candidates:
        pending = [n["id"] for n in manifest["nodes"] if n["status"] == "pending"]
        running = [n["id"] for n in manifest["nodes"] if n["status"] == "running"]
        write_manifest(root, wf_id, manifest)
        return {"status": "blocked", "dispatched": [], "pending": pending, "running": running}

    dispatched: list[str] = []
    for entry in candidates:
        node_def = read_node(root, wf_id, entry["id"])
        started_at = _now()

        # mark running and increment attempt_count
        entry["status"] = "running"
        entry["attempt_count"] = entry.get("attempt_count", 0) + 1
        entry["last_started_at"] = started_at
        write_manifest(root, wf_id, manifest)

        try:
            result = _dispatch_node(node_def, root)
            returncode = result["returncode"]
            output = result.get("output", "")
        except FileNotFoundError as exc:
            returncode = 1
            output = f"executor not found: {node_def.get('executor', 'codex')}"

        completed_at = _now()
        entry["last_completed_at"] = completed_at

        if returncode == 0:
            entry["status"] = "completed"
            entry["last_error"] = None
        else:
            entry["status"] = "failed"
            entry["last_error"] = output[:500] if output else "non-zero exit"

        transition: TransitionEntry = {
            "node": entry["id"],
            "status": "completed" if returncode == 0 else "failed",
            "started_at": started_at,
            "completed_at": completed_at,
            "artifacts_created": node_def.get("exit_artifacts", []),
            "error": entry["last_error"],
        }
        append_transition(root, wf_id, transition)
        dispatched.append(entry["id"])

        # Check if this node exceeded max attempts → fail the whole workflow
        if entry["status"] == "failed" and entry["attempt_count"] >= MAX_ATTEMPTS:
            manifest["workflow_status"] = "failed"
            write_manifest(root, wf_id, manifest)
            _sync_index_status(root, wf_id, "failed")
            return {"status": "workflow_failed", "dispatched": dispatched}

    write_manifest(root, wf_id, manifest)
    return {"status": "ok", "dispatched": dispatched}
```

- [ ] **Step 4: Run all engine tests**

```bash
uv run python -m pytest tests/test_workflow_engine.py -v
```

Expected: `20 passed`

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
uv run python -m pytest -q
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add src/devforge/workflow/engine.py tests/test_workflow_engine.py
git commit -m "feat: implement run_one_cycle with executor dispatch, retry tracking, and failure thresholds"
```

---

### Task 7: `session.py` — add wf IntentKind values

**Files:**
- Modify: `src/devforge/session.py:33-45`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflow_engine.py

from devforge.session import UserIntent


def test_user_intent_accepts_wf_kinds() -> None:
    intents = [
        UserIntent(kind="show_workflow"),
        UserIntent(kind="run_workflow"),
        UserIntent(kind="init_workflow"),
        UserIntent(kind="confirm_workflow"),
        UserIntent(kind="log_workflow"),
        UserIntent(kind="reset_workflow_node", payload={"node_id": "discover"}),
        UserIntent(kind="list_workflows"),
        UserIntent(kind="switch_workflow", payload={"wf_id": "wf-test-001"}),
    ]
    assert all(i.kind.endswith("workflow") or "workflow" in i.kind for i in intents)
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_engine.py::test_user_intent_accepts_wf_kinds -v
```

Expected: `FAILED` — `UserIntent` raises error on unknown kind

- [ ] **Step 3: Update `IntentKind` in `src/devforge/session.py`**

Find the `IntentKind` Literal and add the new values:

```python
IntentKind = Literal[
    "continue_cycle",
    "show_status",
    "list_runs",
    "list_work_packages",
    "observe_run",
    "attach_run",
    "detach_run",
    "interrupt_run",
    "apply_run_result",
    "merge_run_results",
    "input_information",
    "quit_session",
    # workflow engine
    "show_workflow",
    "run_workflow",
    "init_workflow",
    "confirm_workflow",
    "log_workflow",
    "reset_workflow_node",
    "list_workflows",
    "switch_workflow",
]
```

- [ ] **Step 4: Run the test**

```bash
uv run python -m pytest tests/test_workflow_engine.py::test_user_intent_accepts_wf_kinds -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full suite**

```bash
uv run python -m pytest -q
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add src/devforge/session.py tests/test_workflow_engine.py
git commit -m "feat: add workflow IntentKind values to session model"
```

---

### Task 8: `repl.py` — wf command parsing, rendering, and handlers

**Files:**
- Modify: `src/devforge/repl.py`

- [ ] **Step 1: Add wf command parsing to `parse_user_intent`**

In `src/devforge/repl.py`, in `parse_user_intent()` after the existing quit block, add:

```python
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
```

- [ ] **Step 2: Add wf rendering functions** (add before `_render_runs` in `repl.py`)

```python
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
```

- [ ] **Step 3: Add `_init_workflow` helper**

```python
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

    planner_node: NodeDefinition = {
        "id": "planner",
        "capability": "planning",
        "goal": f"分析目标并制定执行计划: {name}",
        "exit_artifacts": [],
        "knowledge_refs": [],
        "executor": "claude_code",
        "mode": "planning",
    }

    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": name,
        "created_at": created_at,
        "workflow_status": "planning",
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
            entry["status"] = "paused"
    index["workflows"].append({
        "id": wf_id,
        "goal": name,
        "status": "active",
        "created_at": created_at,
    })
    index["active_workflow_id"] = wf_id
    write_index(root, index)

    return [
        f"✅ 工作流已创建: {wf_id}",
        f"目标: {name}",
        "Planner 节点已就绪。输入 'wf run' 开始规划。",
    ]
```

- [ ] **Step 4: Add `_confirm_workflow` helper**

```python
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
        manifest["workflow_status"] = "running"
        write_manifest(root, wf_id, manifest)
        return [
            f"✅ 计划已确认，{len(data['nodes'])} 个节点加入工作流。",
            "输入 'wf run' 开始执行。",
        ]
    elif answer == "n":
        # Delete node files and pending plan, reset planner node
        import shutil
        plan_path.unlink(missing_ok=True)
        for node_def in data["nodes"]:
            node_file = root / ".devforge" / "workflows" / wf_id / "nodes" / f"{node_def['id']}.json"
            node_file.unlink(missing_ok=True)
        for node in manifest["nodes"]:
            if node["id"] == "planner":
                node["status"] = "pending"
                node["last_error"] = None
        manifest["workflow_status"] = "planning"
        write_manifest(root, wf_id, manifest)
        return ["❌ 计划已拒绝，Planner 节点重置为 pending。输入 'wf run' 重新规划。"]
    else:
        return ["Usage: wf confirm y | wf confirm n"]
```

- [ ] **Step 5: Add wf intent handlers in the main REPL loop**

In `run_interactive_session`, after the `if intent.kind == "list_work_packages":` block, add:

```python
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
```

- [ ] **Step 6: Update startup goal integration**

In `run_interactive_session`, update the block after the goal prompt to show workflow status on startup if active:

```python
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
```

- [ ] **Step 7: Run the full test suite**

```bash
uv run python -m pytest -q
```

Expected: all passing

- [ ] **Step 8: Manual smoke test**

```bash
make install
devforge
# at the devforge> prompt:
wf list          # → No workflows found.
wf init 逆向分析  # → ✅ 工作流已创建, Planner 节点已就绪
wf               # → shows DAG with 1 pending planner node
wf log           # → No transitions recorded yet.
q
```

- [ ] **Step 9: Commit**

```bash
git add src/devforge/repl.py src/devforge/session.py
git commit -m "feat: add wf commands to REPL (show, run, init, confirm, log, list, reset, switch)"
```
