# Workflow Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone workflow engine that reads `.devforge/workflows/`, executes nodes via Codex/Claude, tracks artifacts and transitions, and exposes `wf` commands in the REPL — replacing meta-skill's `/run` without touching the existing run_cycle machinery.

**Architecture:** New `src/devforge/workflow/` module (models, artifacts, store, engine) with token-efficient file splitting (index/manifest/node/transitions separate files). REPL gets new `wf` intent kinds and handlers. Engine calls executors via subprocess, consistent with how `run_executor_doctor` calls Codex.

**Tech Stack:** Python 3.12, TypedDict, pathlib, subprocess, jsonlines (append-only transitions), uv, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/devforge/workflow/__init__.py` | Create | Export `WorkflowEngine`, `run_one_cycle` |
| `src/devforge/workflow/models.py` | Create | All TypedDict/Literal definitions |
| `src/devforge/workflow/artifacts.py` | Create | exit_artifacts existence checking |
| `src/devforge/workflow/store.py` | Create | Read/write index, manifest, node, transitions |
| `src/devforge/workflow/engine.py` | Create | select_next_nodes, reconcile, run_one_cycle |
| `src/devforge/session.py` | Modify | Add wf IntentKind values |
| `src/devforge/repl.py` | Modify | wf command parsing, rendering, handlers, startup |
| `tests/test_workflow_models.py` | Create | TypedDict shape verification |
| `tests/test_workflow_artifacts.py` | Create | Artifact checking unit tests |
| `tests/test_workflow_store.py` | Create | Store read/write round-trip tests |
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
    NodeStatus,
    WorkflowStatus,
)


def test_node_manifest_entry_is_dict() -> None:
    entry: NodeManifestEntry = {
        "id": "discover",
        "status": "pending",
        "depends_on": [],
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "executor": "codex",
        "parent_node_id": None,
        "depth": 0,
        "error": None,
    }
    assert isinstance(entry, dict)
    assert entry["status"] == "pending"


def test_node_definition_is_dict() -> None:
    node: NodeDefinition = {
        "id": "discover",
        "capability": "discovery",
        "goal": "Scan the repo",
        "exit_artifacts": [".devforge/artifacts/summary.json"],
        "knowledge_refs": ["src/devforge/knowledge/content/capabilities/discovery.md"],
        "executor": "codex",
    }
    assert node["capability"] == "discovery"


def test_workflow_manifest_is_dict() -> None:
    manifest: WorkflowManifest = {
        "id": "wf-test-001",
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
        "nodes": [],
    }
    assert manifest["nodes"] == []


def test_workflow_index_is_dict() -> None:
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": "wf-test-001",
        "workflows": [],
    }
    assert index["schema_version"] == "1.0"
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
WorkflowStatus = Literal["active", "completed", "paused", "failed"]


class NodeManifestEntry(TypedDict):
    id: str
    status: NodeStatus
    depends_on: list[str]
    exit_artifacts: list[str]
    executor: str
    parent_node_id: str | None
    depth: int
    error: str | None


class NodeDefinition(TypedDict):
    id: str
    capability: str
    goal: str
    exit_artifacts: list[str]
    knowledge_refs: list[str]
    executor: str


class WorkflowManifest(TypedDict):
    id: str
    goal: str
    created_at: str
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
```

- [ ] **Step 4: Create `src/devforge/workflow/__init__.py`**

```python
"""DevForge workflow engine."""

from devforge.workflow.engine import run_one_cycle
from devforge.workflow.models import (
    NodeDefinition,
    NodeManifestEntry,
    NodeStatus,
    TransitionEntry,
    WorkflowIndex,
    WorkflowIndexEntry,
    WorkflowManifest,
    WorkflowStatus,
)

__all__ = [
    "run_one_cycle",
    "NodeDefinition",
    "NodeManifestEntry",
    "NodeStatus",
    "TransitionEntry",
    "WorkflowIndex",
    "WorkflowIndexEntry",
    "WorkflowManifest",
    "WorkflowStatus",
]
```

- [ ] **Step 5: Run the test**

```bash
uv run python -m pytest tests/test_workflow_models.py -v
```

Expected: `4 passed`

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
import pytest
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run python -m pytest tests/test_workflow_artifacts.py -v
```

Expected: `ImportError: cannot import name 'check_artifacts'`

- [ ] **Step 3: Create `src/devforge/workflow/artifacts.py`**

```python
"""exit_artifacts existence checking for the workflow engine."""

from __future__ import annotations

from pathlib import Path


def check_artifacts(root: Path, paths: list[str]) -> bool:
    """Return True iff every path in paths exists relative to root."""
    return all((root / p).exists() for p in paths)
```

- [ ] **Step 4: Run the test**

```bash
uv run python -m pytest tests/test_workflow_artifacts.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/artifacts.py tests/test_workflow_artifacts.py
git commit -m "feat: add workflow artifact existence checker"
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
import pytest
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
        "nodes": [
            {
                "id": "discover",
                "status": "pending",
                "depends_on": [],
                "exit_artifacts": [".devforge/artifacts/summary.json"],
                "executor": "codex",
                "parent_node_id": None,
                "depth": 0,
                "error": None,
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
"""

from __future__ import annotations

import json
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


def read_index(root: Path) -> WorkflowIndex:
    path = _index_path(root)
    if not path.exists():
        return dict(_EMPTY_INDEX)  # type: ignore[return-value]
    return json.loads(path.read_text(encoding="utf-8"))


def write_index(root: Path, index: WorkflowIndex) -> None:
    path = _index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_manifest(root: Path, wf_id: str) -> WorkflowManifest:
    path = _manifest_path(root, wf_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(root: Path, wf_id: str, manifest: WorkflowManifest) -> None:
    path = _manifest_path(root, wf_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def active_workflow_id(root: Path) -> str | None:
    return read_index(root)["active_workflow_id"]
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_workflow_store.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/store.py tests/test_workflow_store.py
git commit -m "feat: add workflow store file I/O layer"
```

---

### Task 4: `engine.py` — node selection and artifact reconciliation

**Files:**
- Create: `src/devforge/workflow/engine.py`
- Create: `tests/test_workflow_engine.py` (partial)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_engine.py
from pathlib import Path
import pytest
from devforge.workflow.models import NodeManifestEntry, WorkflowManifest
from devforge.workflow.engine import select_next_nodes, reconcile_artifacts


def _node(
    node_id: str,
    status: str = "pending",
    depends_on: list[str] | None = None,
    exit_artifacts: list[str] | None = None,
) -> NodeManifestEntry:
    return {
        "id": node_id,
        "status": status,  # type: ignore[typeddict-item]
        "depends_on": depends_on or [],
        "exit_artifacts": exit_artifacts or [],
        "executor": "codex",
        "parent_node_id": None,
        "depth": 0,
        "error": None,
    }


def _manifest(nodes: list[NodeManifestEntry]) -> WorkflowManifest:
    return {"id": "wf-test", "goal": "test", "created_at": "2026-04-11T00:00:00Z", "nodes": nodes}


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
    read_manifest,
    read_node,
    read_transitions,
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
        and set(n["depends_on"]) <= completed_ids
    ][:slots]


def reconcile_artifacts(root: Path, manifest: WorkflowManifest) -> WorkflowManifest:
    """Mark nodes completed if all their exit_artifacts exist on disk (files are ground truth)."""
    updated = copy.deepcopy(manifest)
    for node in updated["nodes"]:
        if node["status"] in ("pending", "running") and node["exit_artifacts"]:
            if check_artifacts(root, node["exit_artifacts"]):
                node["status"] = "completed"
                node["error"] = None
    return updated


def run_one_cycle(root: Path) -> dict[str, Any]:
    """Execute one workflow cycle: reconcile → select → dispatch → persist."""
    ...  # implemented in Task 5
```

- [ ] **Step 4: Run the tests**

```bash
uv run python -m pytest tests/test_workflow_engine.py -v
```

Expected: `9 passed` (run_one_cycle tests not written yet)

- [ ] **Step 5: Commit**

```bash
git add src/devforge/workflow/engine.py tests/test_workflow_engine.py
git commit -m "feat: add workflow node selection and artifact reconciliation"
```

---

### Task 5: `engine.py` — `run_one_cycle` with executor dispatch

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


def _setup_workflow(tmp_path: Path, nodes_status: dict[str, str] | None = None) -> None:
    wf_id = "wf-test-001"
    index: WorkflowIndex = {
        "schema_version": "1.0",
        "active_workflow_id": wf_id,
        "workflows": [{"id": wf_id, "goal": "Test", "status": "active", "created_at": "2026-04-11T00:00:00Z"}],
    }
    write_index(tmp_path, index)

    nodes_status = nodes_status or {"discover": "pending"}
    manifest_nodes: list[NodeManifestEntry] = []
    for node_id, status in nodes_status.items():
        manifest_nodes.append(_node(node_id, status=status))
    manifest: WorkflowManifest = {
        "id": wf_id,
        "goal": "Test workflow",
        "created_at": "2026-04-11T00:00:00Z",
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
    from devforge.workflow.store import read_manifest
    manifest = read_manifest(tmp_path, "wf-test-001")
    assert manifest["nodes"][0]["status"] == "completed"


def test_run_one_cycle_marks_node_failed_on_error(tmp_path: Path) -> None:
    _setup_workflow(tmp_path)
    with patch("devforge.workflow.engine._dispatch_node") as mock_dispatch:
        mock_dispatch.return_value = {"returncode": 1, "output": "error msg", "executor": "codex"}
        run_one_cycle(tmp_path)
    from devforge.workflow.store import read_manifest
    manifest = read_manifest(tmp_path, "wf-test-001")
    assert manifest["nodes"][0]["status"] == "failed"
    assert manifest["nodes"][0]["error"] == "error msg"


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


def test_run_one_cycle_returns_no_active_workflow_when_missing(tmp_path: Path) -> None:
    result = run_one_cycle(tmp_path)
    assert result["status"] == "no_active_workflow"
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run python -m pytest tests/test_workflow_engine.py::test_run_one_cycle_dispatches_pending_node -v
```

Expected: `FAILED` — `run_one_cycle` returns `None` (stub)

- [ ] **Step 3: Implement `_dispatch_node` and `run_one_cycle` in `engine.py`**

Replace the stub `run_one_cycle` and add `_dispatch_node`:

```python
def _load_knowledge(refs: list[str], root: Path) -> str:
    """Read knowledge_refs files and join their content."""
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


def run_one_cycle(root: Path) -> dict[str, Any]:
    """Execute one workflow cycle: reconcile → select → dispatch → persist."""
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return {"status": "no_active_workflow", "dispatched": []}

    manifest = read_manifest(root, wf_id)
    manifest = reconcile_artifacts(root, manifest)

    all_done = all(n["status"] == "completed" for n in manifest["nodes"])
    if all_done:
        write_manifest(root, wf_id, manifest)
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

        # mark running
        entry["status"] = "running"
        write_manifest(root, wf_id, manifest)

        result = _dispatch_node(node_def, root)
        completed_at = _now()

        if result["returncode"] == 0:
            entry["status"] = "completed"
            entry["error"] = None
        else:
            entry["status"] = "failed"
            entry["error"] = result["output"][:500] if result["output"] else "non-zero exit"

        transition: TransitionEntry = {
            "node": entry["id"],
            "status": "completed" if result["returncode"] == 0 else "failed",
            "started_at": started_at,
            "completed_at": completed_at,
            "artifacts_created": node_def.get("exit_artifacts", []),
            "error": entry["error"],
        }
        append_transition(root, wf_id, transition)
        dispatched.append(entry["id"])

    write_manifest(root, wf_id, manifest)
    return {"status": "ok", "dispatched": dispatched}
```

- [ ] **Step 4: Run all engine tests**

```bash
uv run python -m pytest tests/test_workflow_engine.py -v
```

Expected: `15 passed`

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
uv run python -m pytest -q
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add src/devforge/workflow/engine.py tests/test_workflow_engine.py
git commit -m "feat: implement run_one_cycle with executor dispatch"
```

---

### Task 6: `session.py` — add wf IntentKind values

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

Expected: `FAILED` — `UserIntent` raises error on unknown kind (or mypy would reject it)

- [ ] **Step 3: Update `IntentKind` in `src/devforge/session.py`**

Find the `IntentKind` Literal (lines 33-45) and add the new values:

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

### Task 7: `repl.py` — wf command parsing, rendering, and handlers

**Files:**
- Modify: `src/devforge/repl.py`

- [ ] **Step 1: Add wf command parsing to `parse_user_intent`**

In `src/devforge/repl.py`, in `parse_user_intent()` after the existing quit block (around line 54), add:

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
```

- [ ] **Step 3: Add `_init_workflow` helper**

```python
def _init_workflow(root: Path, name: str) -> list[str]:
    """Create a new empty workflow and set it as active."""
    import re
    from datetime import datetime, timezone
    from devforge.workflow.store import read_index, write_index, write_manifest
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name).strip("-")[:40]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    wf_id = f"wf-{slug}-{ts}"
    manifest = {
        "id": wf_id,
        "goal": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nodes": [],
    }
    write_manifest(root, wf_id, manifest)
    index = read_index(root)
    index["workflows"].append({"id": wf_id, "goal": name, "status": "active", "created_at": manifest["created_at"]})
    index["active_workflow_id"] = wf_id
    write_index(root, index)
    return [f"✅ 工作流已创建: {wf_id}", f"目标: {name}", "使用 'wf' 查看状态，'wf run' 开始执行。"]
```

- [ ] **Step 4: Add wf intent handlers in the main REPL loop**

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
            elif result["status"] == "all_complete":
                output_fn("✅ Workflow complete — all nodes finished.")
            elif result["status"] == "blocked":
                output_fn(f"⚠ Blocked — no runnable nodes. Pending: {result.get('pending', [])}")
            else:
                output_fn(f"Dispatched: {', '.join(result['dispatched'])}")
                for line in _render_workflow(root_path):
                    output_fn(line)
            continue

        if intent.kind == "init_workflow":
            name = intent.payload.get("name", "").strip()
            if not name:
                output_fn("Usage: wf init <工作流名称>")
            else:
                for line in _init_workflow(root_path, name):
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
            node_id = intent.payload.get("node_id", "")
            from devforge.workflow.store import active_workflow_id, read_manifest, write_manifest
            wf_id = active_workflow_id(root_path)
            if not wf_id:
                output_fn("No active workflow.")
            else:
                manifest = read_manifest(root_path, wf_id)
                for n in manifest["nodes"]:
                    if n["id"] == node_id:
                        n["status"] = "pending"
                        n["error"] = None
                        write_manifest(root_path, wf_id, manifest)
                        output_fn(f"✅ Node '{node_id}' reset to pending.")
                        break
                else:
                    output_fn(f"Node '{node_id}' not found in active workflow.")
            continue

        if intent.kind == "switch_workflow":
            wf_id = intent.payload.get("wf_id", "")
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

- [ ] **Step 5: Update startup goal integration**

In `run_interactive_session`, update the block after the goal prompt:

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

- [ ] **Step 6: Run the full test suite**

```bash
uv run python -m pytest -q
```

Expected: all passing (wf commands are UI-only, not unit-tested directly)

- [ ] **Step 7: Manual smoke test**

```bash
make install
devforge
# at the devforge> prompt:
wf list          # → No workflows found.
wf init 逆向分析  # → ✅ 工作流已创建
wf              # → shows DAG (0 nodes)
wf log          # → No transitions recorded yet.
q
```

- [ ] **Step 8: Commit**

```bash
git add src/devforge/repl.py src/devforge/session.py
git commit -m "feat: add wf commands to REPL (show, run, init, log, list, reset, switch)"
```
