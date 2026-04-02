"""Executor adapters with executor-specific request shaping."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from devforge.context import ContextBroker, ResolvedContext
from devforge.state import ExecutorResult, Finding, WorkPackage

from .base import ClaudeCodeTaskRequest, CodexTaskRequest, ExecutorDispatch, SubmissionReceipt
from .payloads import format_executor_payload
from .pull_policy import resolve_pull_strategy


@dataclass(slots=True)
class BaseExecutorAdapter:
    """Base adapter with shared support checks and stub lifecycle methods."""

    name: str
    supported_phases: tuple[str, ...]
    supported_roles: tuple[str, ...]

    def supports_phase(self, phase: str) -> bool:
        return phase in self.supported_phases

    def supports_role(self, role_id: str) -> bool:
        return role_id in self.supported_roles

    def estimate(self, work_package: WorkPackage) -> dict[str, Any]:
        return {
            "executor": self.name,
            "work_package_id": work_package.work_package_id,
            "supports_phase": self.supports_phase(work_package.phase),
            "supports_role": self.supports_role(work_package.role_id),
        }

    def build_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Build an executor-facing request payload."""
        return {
            "executor": self.name,
            "work_package_id": work_package.work_package_id,
            "cycle_id": runtime_context.get("cycle_id"),
            "payload": format_executor_payload(self.name, runtime_context),
        }

    def prepare_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Prepare an executor-specific request object."""
        return self.build_request(work_package, runtime_context)

    def _request_to_dict(self, request: dict[str, Any] | Any) -> dict[str, Any]:
        if isinstance(request, dict):
            return request
        if is_dataclass(request):
            return asdict(request)
        raise TypeError(f"Unsupported request type for {self.name}: {type(request)!r}")

    def _execution_ref(
        self,
        *,
        cycle_id: str | None,
        work_package_id: str,
        execution_id: str,
    ) -> dict[str, str | None]:
        return {
            "cycle_id": cycle_id,
            "work_package_id": work_package_id,
            "executor": self.name,
            "execution_id": execution_id,
        }

    def submit(self, request: dict[str, Any] | Any) -> SubmissionReceipt:
        """Transport boundary. Replace this for real executor integrations."""
        request_dict = self._request_to_dict(request)
        return SubmissionReceipt(
            execution_id="%s:%s" % (self.name, request_dict["work_package_id"]),
            accepted=True,
            message="stub transport submitted",
            metadata={"transport": "stub"},
        )

    def submit_request(self, request: dict[str, Any], *, accepted: bool) -> ExecutorDispatch:
        """Submit a prepared request and normalize it into orchestration dispatch metadata."""
        request_dict = self._request_to_dict(request)
        receipt = self.submit(request)
        dispatch_accepted = accepted and receipt.accepted
        message = receipt.message if dispatch_accepted else "executor rejected unsupported work package"
        return ExecutorDispatch(
            execution_id=receipt.execution_id,
            executor=self.name,
            work_package_id=request_dict["work_package_id"],
            accepted=dispatch_accepted,
            message=message,
            metadata={
                "accepted": dispatch_accepted,
                "executor_payload": request_dict.get("payload", {}),
                "executor_request": request_dict,
                "cycle_id": request_dict.get("cycle_id"),
                "execution_ref": self._execution_ref(
                    cycle_id=request_dict.get("cycle_id"),
                    work_package_id=request_dict["work_package_id"],
                    execution_id=receipt.execution_id,
                ),
                "submission_receipt": {
                    "execution_id": receipt.execution_id,
                    "accepted": receipt.accepted,
                    "message": receipt.message,
                    "metadata": receipt.metadata,
                },
            },
        )

    def dispatch(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> ExecutorDispatch:
        accepted = self.supports_phase(work_package.phase) and self.supports_role(work_package.role_id)
        request = self.prepare_request(work_package, runtime_context)
        dispatch = self.submit_request(request, accepted=accepted)
        dispatch.metadata["runtime_context"] = runtime_context
        return dispatch

    def default_pull_strategy(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Default on-demand pull behavior when no executor-specific override exists."""
        manifest = runtime_context.get("context_pull_manifest", {})
        return resolve_pull_strategy(
            self.name,
            work_package,
            list(manifest.get("refs", [])),
            project_archetype=runtime_context.get("project_archetype"),
            override_rules=runtime_context.get("project_pull_policy_overrides"),
        )

    def pull_context(
        self,
        refs: list[str],
        *,
        broker: ContextBroker,
        mode: str = "summary",
        budget: int | None = None,
    ) -> list[ResolvedContext]:
        """Pull additional context through the shared broker boundary."""
        return broker.resolve_context_bundle(refs, mode=mode, budget=budget)

    def poll(self, execution_id: str) -> dict[str, Any]:
        return {"execution_id": execution_id, "status": "completed", "summary": "stub poll"}

    def cancel(self, execution_id: str) -> dict[str, Any]:
        return {"execution_id": execution_id, "status": "cancelled"}

    def normalize_result(self, raw_result: dict[str, Any]) -> ExecutorResult:
        raw_status = raw_result.get("status", "completed")
        findings = [
            item if isinstance(item, Finding) else Finding(**item)
            for item in raw_result.get("findings", [])
        ]
        return ExecutorResult(
            execution_id=raw_result["execution_id"],
            executor=self.name,
            work_package_id=raw_result.get("work_package_id", ""),
            cycle_id=raw_result.get("cycle_id"),
            status=raw_status,
            summary=raw_result.get("summary", "stub result"),
            execution_ref=self._execution_ref(
                cycle_id=raw_result.get("cycle_id"),
                work_package_id=raw_result.get("work_package_id", ""),
                execution_id=raw_result["execution_id"],
            ),
            artifacts_created=raw_result.get("artifacts_created", []),
            artifacts_modified=raw_result.get("artifacts_modified", []),
            tests_run=raw_result.get("tests_run", []),
            findings=findings,
            handoff_notes=raw_result.get("handoff_notes", []),
            raw_output_ref=raw_result.get("raw_output_ref"),
            started_at=raw_result.get("started_at"),
            completed_at=raw_result.get("completed_at"),
        )


class PythonAdapter(BaseExecutorAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="python",
            supported_phases=("concept_collect", "acceptance", "requirement_patch"),
            supported_roles=("product_manager", "execution_planner", "integration_owner"),
        )


class ClaudeCodeAdapter(BaseExecutorAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="claude_code",
            supported_phases=("concept_collect", "analysis_design", "implementation", "testing", "acceptance"),
            supported_roles=(
                "product_manager",
                "execution_planner",
                "interaction_designer",
                "ui_designer",
                "technical_architect",
                "software_engineer",
                "qa_engineer",
                "integration_owner",
            ),
        )

    def build_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> ClaudeCodeTaskRequest:
        payload = format_executor_payload(self.name, runtime_context)
        return ClaudeCodeTaskRequest(
            executor=self.name,
            mode="delegated_session",
            task_type="architect_or_builder",
            work_package_id=work_package.work_package_id,
            cycle_id=runtime_context.get("cycle_id"),
            goal=work_package.goal,
            payload=payload,
            references=payload.get("references", []),
        )

    def prepare_request(
        self, work_package: WorkPackage, runtime_context: dict[str, Any]
    ) -> ClaudeCodeTaskRequest:
        return self.build_request(work_package, runtime_context)

    def submit_request(self, request: dict[str, Any] | ClaudeCodeTaskRequest, *, accepted: bool) -> ExecutorDispatch:
        dispatch = super().submit_request(request, accepted=accepted)
        dispatch.message = "claude_code request accepted" if dispatch.accepted else "claude_code request rejected"
        dispatch.metadata["submit_boundary"] = "claude_code.submit_request"
        return dispatch


class CodexAdapter(BaseExecutorAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="codex",
            supported_phases=("analysis_design", "implementation", "testing"),
            supported_roles=("technical_architect", "software_engineer", "qa_engineer"),
        )

    def build_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> CodexTaskRequest:
        payload = format_executor_payload(self.name, runtime_context)
        return CodexTaskRequest(
            executor=self.name,
            mode="task_payload",
            task_type="implementation_or_qa",
            work_package_id=work_package.work_package_id,
            cycle_id=runtime_context.get("cycle_id"),
            goal=work_package.goal,
            deliverables=work_package.deliverables,
            payload=payload,
        )

    def prepare_request(self, work_package: WorkPackage, runtime_context: dict[str, Any]) -> CodexTaskRequest:
        """Prepare a strongly-shaped Codex task request."""
        return self.build_request(work_package, runtime_context)

    def submit_request(self, request: dict[str, Any] | CodexTaskRequest, *, accepted: bool) -> ExecutorDispatch:
        """Stub submit boundary for Codex. Replace here for real integration later."""
        dispatch = super().submit_request(request, accepted=accepted)
        dispatch.message = "codex request accepted" if dispatch.accepted else "codex request rejected"
        dispatch.metadata["submit_boundary"] = "codex.submit_request"
        return dispatch

class ClineAdapter(BaseExecutorAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="cline",
            supported_phases=("implementation", "testing"),
            supported_roles=("software_engineer", "qa_engineer"),
        )


class OpenCodeAdapter(BaseExecutorAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="opencode",
            supported_phases=("analysis_design",),
            supported_roles=("interaction_designer", "ui_designer"),
        )
