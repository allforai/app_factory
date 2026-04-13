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
    PullContextEvent,
    TransitionEntry,
    WorkflowIndex,
    WorkflowIntent,
    WorkflowManifest,
)

_WORKFLOWS_DIR = ".devforge/workflows"
_INDEX_FILE = "index.json"
_MANIFEST_FILE = "manifest.json"
_CURRENT_INTENT_FILE = "current_intent.json"
_TRANSITIONS_FILE = "transitions.jsonl"
_PULL_EVENTS_FILE = "pull_events.jsonl"


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


def _intent_path(root: Path, wf_id: str) -> Path:
    return _wf_dir(root, wf_id) / _CURRENT_INTENT_FILE


def _transitions_path(root: Path, wf_id: str) -> Path:
    return _wf_dir(root, wf_id) / _TRANSITIONS_FILE


def _pull_events_path(root: Path, wf_id: str) -> Path:
    return _wf_dir(root, wf_id) / _PULL_EVENTS_FILE


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
        return {"schema_version": "1.0", "active_workflow_id": None, "workflows": []}
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


def read_current_intent(root: Path, wf_id: str) -> WorkflowIntent:
    path = _intent_path(root, wf_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    manifest = read_manifest(root, wf_id)
    fallback: WorkflowIntent = {
        "goal": manifest.get("goal", ""),
        "updated_at": manifest.get("created_at", ""),
        "updated_by": "manifest-fallback",
        "lessons_learned": [],
        "active_hypotheses": [],
    }
    write_current_intent(root, wf_id, fallback)
    return fallback


def write_current_intent(root: Path, wf_id: str, intent: WorkflowIntent) -> None:
    _atomic_write(
        _intent_path(root, wf_id),
        json.dumps(intent, ensure_ascii=False, indent=2) + "\n",
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


def append_pull_event(root: Path, wf_id: str, entry: PullContextEvent) -> None:
    path = _pull_events_path(root, wf_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_pull_events(root: Path, wf_id: str) -> list[PullContextEvent]:
    path = _pull_events_path(root, wf_id)
    if not path.exists():
        return []
    result: list[PullContextEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


def active_workflow_id(root: Path) -> str | None:
    return read_index(root)["active_workflow_id"]
