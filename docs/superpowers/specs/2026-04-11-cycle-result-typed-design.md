# Design: CycleResult TypedDict

**Date:** 2026-04-11  
**Scope:** `src/devforge/graph/builder.py` (and two call sites)  
**Goal:** Replace `dict[str, Any]` return type on `run_cycle()` with a typed `CycleResult` TypedDict, improving IDE discoverability and catching key-name typos at type-check time — with zero changes to existing callers.

---

## Problem

`run_cycle()` currently returns `dict[str, Any]`. Callers must know the six key names (`runtime`, `selected_work_packages`, `dispatches`, `results`, `events`, `snapshot`) by convention. There is no IDE completion, no mypy checking, and no documentation of what the dict contains.

## Approach

Use a `TypedDict` — a Python type that is structurally identical to a plain `dict` at runtime, but carries field-level type annotations that IDEs and mypy can use. Callers continue to write `result["snapshot"]`, `result["dispatches"]`, etc. No behaviour changes, no migration required.

Alternative considered and rejected: a proper `dataclass` (option a) would require ~50+ callsite changes; a `dict`-subclassing dataclass (option b) adds runtime complexity with no upside over TypedDict for this use case.

## Definition

```python
from typing import TypedDict, Any

class CycleResult(TypedDict):
    runtime: dict[str, Any]           # asdict(RuntimeState)
    selected_work_packages: list[str]
    dispatches: list[dict[str, Any]]
    results: list[dict[str, Any]]
    events: list[dict[str, Any]]
    snapshot: dict[str, Any]
```

Nested dicts (`runtime`, `dispatches`, `results`) are left as `dict[str, Any]` — typing their internals is out of scope.

## Files Changed

| File | Change |
|------|--------|
| `src/devforge/graph/builder.py` | Add `CycleResult` TypedDict definition; change `run_cycle()` return annotation to `-> CycleResult` |
| `src/devforge/main.py` | Update `run_fixture_cycle()` and `run_snapshot_cycle()` return annotations to `-> CycleResult` |

**Zero changes** to tests or any other caller.

## Placement

`CycleResult` is defined at the top of `builder.py`, near the existing imports. It is not added to `__init__.py` — it's an internal type for now.

## Testing

No new tests required. Existing 256-test suite verifies behaviour is unchanged. A `uv run python -m pytest -q` green run is the acceptance criterion.
