# CycleResult TypedDict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `dict[str, Any]` return type on `run_cycle()`, `run_fixture_cycle()`, and `run_snapshot_cycle()` with a typed `CycleResult` TypedDict — zero runtime behaviour changes, zero callsite changes.

**Architecture:** Add a `CycleResult` TypedDict definition to `builder.py` capturing the six keys already returned by `run_cycle()`. Update the three function signatures to use it. All existing tests continue to pass unchanged because `TypedDict` instances are plain `dict` at runtime.

**Tech Stack:** Python 3.12 `typing.TypedDict`, uv, pytest

---

### Task 1: Add `CycleResult` TypedDict and update `run_cycle`

**Files:**
- Modify: `src/devforge/graph/builder.py:8` (imports)
- Modify: `src/devforge/graph/builder.py:1060` (`run_cycle` return annotation)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph_runner.py` (at the top-level, after existing imports):

```python
from devforge.graph.builder import CycleResult


def test_run_cycle_returns_cycle_result_typed_keys() -> None:
    """CycleResult is a TypedDict — verify all declared keys are present."""
    snapshot = {
        "initiative": {
            "initiative_id": "i1",
            "name": "test",
            "goal": "test",
            "status": "active",
            "project_ids": ["p1"],
            "shared_concepts": [],
            "shared_contracts": [],
            "initiative_memory_ref": None,
            "global_acceptance_goals": [],
            "requirement_event_ids": [],
            "scheduler_state": {},
        },
        "projects": [
            {
                "project_id": "p1",
                "initiative_id": "i1",
                "parent_project_id": None,
                "name": "test",
                "kind": "new_product",
                "status": "active",
                "current_phase": "concept_collect",
                "phases": ["concept_collect"],
                "project_archetype": "general",
                "domains": ["core"],
                "active_roles": ["product_manager"],
                "concept_model_refs": [],
                "contracts": [],
                "pull_policy_overrides": [],
                "llm_preferences": {},
                "knowledge_preferences": {},
                "executor_policy_ref": None,
                "work_package_ids": [],
                "seam_ids": [],
                "artifacts": {},
                "project_memory_ref": None,
                "assumptions": [],
                "requirement_events": [],
                "children": [],
                "coordination_project": False,
                "created_at": None,
                "updated_at": None,
            }
        ],
        "work_packages": [],
        "executor_policies": [],
        "requirement_events": [],
        "seams": [],
    }
    result = run_cycle(snapshot)
    # TypedDict keys must all be present
    assert "runtime" in result
    assert "selected_work_packages" in result
    assert "dispatches" in result
    assert "results" in result
    assert "events" in result
    assert "snapshot" in result
    # TypedDict instances are plain dicts at runtime
    assert isinstance(result, dict)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run python -m pytest tests/test_graph_runner.py::test_run_cycle_returns_cycle_result_typed_keys -v
```

Expected: `ImportError: cannot import name 'CycleResult' from 'devforge.graph.builder'`

- [ ] **Step 3: Add `CycleResult` to `builder.py`**

In `src/devforge/graph/builder.py`, change the `typing` import line (currently line 8):

```python
from typing import Any
```

→

```python
from typing import Any, TypedDict


class CycleResult(TypedDict):
    runtime: dict[str, Any]
    selected_work_packages: list[str]
    dispatches: list[dict[str, Any]]
    results: list[dict[str, Any]]
    events: list[dict[str, Any]]
    snapshot: dict[str, Any]
```

- [ ] **Step 4: Update `run_cycle` return annotation**

In `src/devforge/graph/builder.py` at line 1060, change:

```python
) -> dict[str, Any]:
```

→

```python
) -> CycleResult:
```

- [ ] **Step 5: Run the new test**

```bash
uv run python -m pytest tests/test_graph_runner.py::test_run_cycle_returns_cycle_result_typed_keys -v
```

Expected: `PASSED`

- [ ] **Step 6: Run full suite to verify nothing broke**

```bash
uv run python -m pytest -q
```

Expected: `256 passed` (or higher — all passing, none failing)

- [ ] **Step 7: Commit**

```bash
git add src/devforge/graph/builder.py tests/test_graph_runner.py
git commit -m "feat: add CycleResult TypedDict return type to run_cycle"
```

---

### Task 2: Update `run_fixture_cycle` and `run_snapshot_cycle` in `main.py`

**Files:**
- Modify: `src/devforge/main.py:14` (imports)
- Modify: `src/devforge/main.py:41` (`run_fixture_cycle` return annotation)
- Modify: `src/devforge/main.py:55` (`run_snapshot_cycle` return annotation)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main_cli.py`:

```python
from devforge.graph.builder import CycleResult
from devforge.main import run_fixture_cycle, run_snapshot_cycle
import inspect


def test_run_fixture_cycle_annotated_cycle_result() -> None:
    hints = inspect.get_annotations(run_fixture_cycle, eval_str=True)
    assert hints.get("return") is CycleResult


def test_run_snapshot_cycle_annotated_cycle_result() -> None:
    hints = inspect.get_annotations(run_snapshot_cycle, eval_str=True)
    assert hints.get("return") is CycleResult
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run python -m pytest tests/test_main_cli.py::test_run_fixture_cycle_annotated_cycle_result tests/test_main_cli.py::test_run_snapshot_cycle_annotated_cycle_result -v
```

Expected: `FAILED` — both return annotation is still `dict[str, Any]`, not `CycleResult`

- [ ] **Step 3: Update imports in `main.py`**

In `src/devforge/main.py`, find the line that imports from `devforge.graph.builder`:

```python
from devforge.graph.builder import run_cycle
```

Change to:

```python
from devforge.graph.builder import CycleResult, run_cycle
```

- [ ] **Step 4: Update `run_fixture_cycle` return annotation**

In `src/devforge/main.py` line 41, change:

```python
def run_fixture_cycle(fixture_name: str) -> dict[str, Any]:
```

→

```python
def run_fixture_cycle(fixture_name: str) -> CycleResult:
```

- [ ] **Step 5: Update `run_snapshot_cycle` return annotation**

In `src/devforge/main.py` line 50–55, change:

```python
) -> dict[str, Any]:
```

→

```python
) -> CycleResult:
```

- [ ] **Step 6: Run the annotation tests**

```bash
uv run python -m pytest tests/test_main_cli.py::test_run_fixture_cycle_annotated_cycle_result tests/test_main_cli.py::test_run_snapshot_cycle_annotated_cycle_result -v
```

Expected: both `PASSED`

- [ ] **Step 7: Run full suite**

```bash
uv run python -m pytest -q
```

Expected: all passing, none failing

- [ ] **Step 8: Commit**

```bash
git add src/devforge/main.py tests/test_main_cli.py
git commit -m "feat: propagate CycleResult return type to run_fixture_cycle and run_snapshot_cycle"
```
