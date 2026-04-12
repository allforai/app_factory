"""Real subprocess transport for CLI-based executors."""
from __future__ import annotations
import json
import subprocess
import time
from dataclasses import dataclass
from uuid import uuid4


@dataclass(slots=True)
class SubprocessResult:
    execution_id: str
    status: str  # "running", "completed", "failed", "timed_out", "cancelled"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class SubprocessTransport:
    def __init__(self):
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._timeouts: dict[str, float] = {}
        self._start_times: dict[str, float] = {}

    def submit(self, command, working_dir, timeout=300, env=None) -> SubprocessResult:
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
        return SubprocessResult(execution_id=execution_id, status="running")

    def poll(self, execution_id, *, check_timeout=False) -> SubprocessResult:
        process = self._processes.get(execution_id)
        if process is None:
            return SubprocessResult(execution_id=execution_id, status="failed", stderr="unknown execution_id")
        if check_timeout:
            timeout = self._timeouts.get(execution_id, 300)
            start = self._start_times.get(execution_id, -1)
            if start >= 0 and (time.monotonic() - start) > timeout:
                process.terminate()
                return SubprocessResult(execution_id=execution_id, status="timed_out")
        exit_code = process.poll()
        if exit_code is None:
            return SubprocessResult(execution_id=execution_id, status="running")
        stdout, stderr = process.communicate(timeout=5)
        return SubprocessResult(
            execution_id=execution_id,
            status="completed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            stdout=stdout or "",
            stderr=stderr or "",
        )

    def cancel(self, execution_id) -> SubprocessResult:
        process = self._processes.get(execution_id)
        if process is None:
            return SubprocessResult(execution_id=execution_id, status="failed", stderr="unknown execution_id")
        process.terminate()
        return SubprocessResult(execution_id=execution_id, status="cancelled")


def build_claude_code_command(prompt, working_dir, *, model=None, max_turns=None):
    cmd = ["claude", "--print", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])
    cmd.append(prompt)
    return cmd


def build_codex_command(prompt, working_dir, *, model=None):
    cmd = ["codex", "exec", "--full-auto", "--cd", working_dir]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    return cmd


def build_python_local_command(request, working_dir):
    return [
        "python",
        "-m",
        "devforge.executors.local_runner",
        json.dumps(request),
    ]
