# Spec: Migrate Workflow Engine to LangGraph

**Date:** 2026-04-12
**Scope:** src/devforge/workflow/engine.py → src/devforge/workflow/graph.py (new)
**Goal:** Replace hand-written run_one_cycle() with a LangGraph StateGraph while keeping the file-system observability layer (manifest.json, status.json, transitions.jsonl, runs/*.log) fully intact.

---

## Why

Current engine.py uses hand-written if/else for state routing:
- reconcile → select → dispatch → persist (all in one monolithic function)
- routing logic (blocked? complete? failed?) is buried in imperative code
- hard to extend (e.g. parallel dispatch, human-in-the-loop nodes)

LangGraph gives us:
- explicit graph structure — routing is declared, not buried
- conditional edges replace if/else chains
- interrupt_before for human-in-the-loop (replaces awaiting_confirm hack)
- composable nodes — easy to add new steps without touching existing ones

---

## Architecture

### State

```python
class WorkflowState(TypedDict):
    root: str                    # project root path (str, not Path — LangGraph needs serializable)
    wf_id: str
    manifest: WorkflowManifest   # current manifest dict (read from file at start of cycle)
    candidates: list             # selected nodes for this cycle
    dispatched: list[str]        # node ids dispatched this cycle
    cycle_result: str            # "ok" | "all_complete" | "blocked" | "workflow_failed" | "awaiting_confirm"
    blocked_by: list[str]        # exhausted node ids (when workflow_failed)
```

### Graph Nodes

```
START
  │
  ▼
load_manifest          — read manifest.json, put into state
  │
  ▼
reconcile              — check exit_artifacts on disk, mark completed if present
  │
  ▼
check_done             — are all nodes completed?
  │ (conditional)
  ├─ yes ──────────────→ finalize_complete → END
  │
  ▼
check_awaiting_confirm — is workflow_status == "awaiting_confirm"?
  │ (conditional)
  ├─ yes ──────────────→ finalize_awaiting → END
  │
  ▼
select_nodes           — run select_next_nodes(), put candidates in state
  │ (conditional)
  ├─ empty candidates ─→ check_exhausted → finalize_failed or finalize_blocked → END
  │
  ▼
dispatch_nodes         — for each candidate: read node def, run subprocess, write run log, update manifest
  │
  ▼
persist                — write_manifest, write_status_json
  │
  ▼
END  (returns cycle_result)
```

### Key Design Decisions

1. **One cycle = one graph invocation.** `run_one_cycle(root)` becomes `graph.invoke(initial_state)`. The graph always terminates (no infinite loops inside) — looping is done externally by calling `wf run` again.

2. **File system layer is unchanged.** Every node that modifies manifest still calls `write_manifest()`. `status.json` is still written by `persist` node. `transitions.jsonl` is still appended in `dispatch_nodes`.

3. **`interrupt_before="dispatch_nodes"` for awaiting_confirm.** Instead of checking `workflow_status == "awaiting_confirm"` at the start, use LangGraph's built-in interrupt mechanism on the `dispatch_nodes` node when `manifest["workflow_status"] == "planning"` and a planner node just completed. This is cleaner than the current hack.

4. **No LangGraph checkpointing needed for persistence** — we use our own file system. Keep it simple: `MemorySaver` only if needed for interrupt_before, otherwise no checkpointer.

---

## File Changes

| File | Action |
|------|--------|
| `src/devforge/workflow/graph.py` | NEW — LangGraph StateGraph implementation |
| `src/devforge/workflow/engine.py` | MODIFY — `run_one_cycle()` delegates to `graph.py`, keep all helper functions (_dispatch_node, _write_run_log, _write_status_json, etc.) |
| `src/devforge/workflow/__init__.py` | MODIFY — export `run_one_cycle` still (interface unchanged) |

**Public interface is unchanged:** `run_one_cycle(root: Path) -> dict[str, Any]` still works the same way. All CLI commands (`wf run`, etc.) need zero changes.

---

## graph.py Skeleton

```python
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Any
from pathlib import Path

class WorkflowState(TypedDict):
    root: str
    wf_id: str
    manifest: dict
    candidates: list
    dispatched: list
    cycle_result: str
    blocked_by: list

def load_manifest_node(state: WorkflowState) -> WorkflowState: ...
def reconcile_node(state: WorkflowState) -> WorkflowState: ...
def select_nodes_node(state: WorkflowState) -> WorkflowState: ...
def dispatch_nodes_node(state: WorkflowState) -> WorkflowState: ...
def persist_node(state: WorkflowState) -> WorkflowState: ...
def finalize_complete_node(state: WorkflowState) -> WorkflowState: ...
def finalize_failed_node(state: WorkflowState) -> WorkflowState: ...
def finalize_blocked_node(state: WorkflowState) -> WorkflowState: ...
def finalize_awaiting_node(state: WorkflowState) -> WorkflowState: ...

def route_after_reconcile(state: WorkflowState) -> str:
    # "all_complete" | "awaiting_confirm" | "select"
    ...

def route_after_select(state: WorkflowState) -> str:
    # "dispatch" | "exhausted" | "blocked"
    ...

def build_workflow_graph():
    graph = StateGraph(WorkflowState)
    # add nodes and edges per architecture above
    return graph.compile()

_graph = build_workflow_graph()

def run_one_cycle(root: Path) -> dict[str, Any]:
    wf_id = active_workflow_id(root)
    if wf_id is None:
        return {"status": "no_active_workflow", "dispatched": []}
    try:
        manifest = read_manifest(root, wf_id)
    except FileNotFoundError:
        return {"status": "manifest_missing", "dispatched": []}

    initial_state = WorkflowState(
        root=str(root), wf_id=wf_id, manifest=manifest,
        candidates=[], dispatched=[], cycle_result="", blocked_by=[]
    )
    final_state = _graph.invoke(initial_state)
    return {
        "status": final_state["cycle_result"],
        "dispatched": final_state["dispatched"],
        "blocked_by": final_state.get("blocked_by", []),
    }
```

---

## Tests to Pass

All existing tests in `tests/test_workflow_engine.py` must pass unchanged — they test `run_one_cycle()` which has the same signature.
Add new tests in `tests/test_workflow_graph.py` that directly test the graph nodes.
