"""Workflow-scoped lazy context reader for executor subprocesses."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from devforge.workflow.store import append_pull_event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_path(root: Path, requested_path: str) -> Path:
    candidate = Path(requested_path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path must stay within workspace root: {requested_path}") from exc
    return candidate


def pull_context(root: Path, wf_id: str, node_id: str, requested_path: str) -> str:
    resolved = _resolve_path(root, requested_path)
    if not resolved.exists():
        raise FileNotFoundError(f"context path not found: {requested_path}")
    if resolved.is_dir():
        raise IsADirectoryError(f"context path is a directory: {requested_path}")

    try:
        content = resolved.read_text(encoding="utf-8")
        kind = "text"
    except UnicodeDecodeError:
        content = json.dumps(
            {
                "path": str(resolved.relative_to(root)),
                "kind": "binary",
                "bytes": resolved.stat().st_size,
            },
            ensure_ascii=False,
            indent=2,
        )
        kind = "binary"

    append_pull_event(
        root,
        wf_id,
        {
            "event_id": f"pull-{uuid4().hex[:12]}",
            "node_id": node_id,
            "path": str(resolved.relative_to(root)),
            "kind": kind,
            "bytes_read": len(content.encode("utf-8")),
            "created_at": _now(),
        },
    )
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read workflow context on demand and log the pull event.")
    parser.add_argument("path", help="Path to a source file or artifact relative to the workspace root.")
    parser.add_argument("--root", required=True, help="Workspace root path.")
    parser.add_argument("--wf-id", required=True, help="Workflow id for event logging.")
    parser.add_argument("--node-id", required=True, help="Node id requesting the context.")
    args = parser.parse_args(argv)

    content = pull_context(Path(args.root), args.wf_id, args.node_id, args.path)
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
