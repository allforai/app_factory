"""Executor adapter exports."""

from .adapters import ClaudeCodeAdapter, ClineAdapter, CodexAdapter, OpenCodeAdapter, PythonAdapter
from .base import ClaudeCodeTaskRequest, CodexTaskRequest, ExecutorAdapter, ExecutorDispatch, SubmissionReceipt
from .capabilities import ExecutorCapability, get_executor_capability, EXECUTOR_CAPABILITIES
from .granularity import validate_granularity, estimate_package_tokens, suggest_split, suggest_merge, GranularityAction
from .payloads import format_executor_payload
from .pull_policy import PULL_POLICY_OVERRIDE_SCHEMA, PULL_POLICY_RULES, PullPolicyRule, normalize_pull_policy_overrides, resolve_pull_strategy
from .registry import EXECUTOR_REGISTRY, get_executor_adapter, register_executor_adapter
from .subprocess_transport import SubprocessTransport, SubprocessResult, build_claude_code_command, build_codex_command

for _adapter in (
    PythonAdapter(),
    ClaudeCodeAdapter(),
    CodexAdapter(),
    ClineAdapter(),
    OpenCodeAdapter(),
):
    register_executor_adapter(_adapter)

__all__ = [
    "ClaudeCodeAdapter",
    "ClaudeCodeTaskRequest",
    "ClineAdapter",
    "CodexTaskRequest",
    "CodexAdapter",
    "EXECUTOR_CAPABILITIES",
    "EXECUTOR_REGISTRY",
    "ExecutorAdapter",
    "ExecutorCapability",
    "ExecutorDispatch",
    "GranularityAction",
    "SubprocessResult",
    "SubprocessTransport",
    "build_claude_code_command",
    "build_codex_command",
    "estimate_package_tokens",
    "format_executor_payload",
    "get_executor_capability",
    "OpenCodeAdapter",
    "PULL_POLICY_OVERRIDE_SCHEMA",
    "PythonAdapter",
    "PULL_POLICY_RULES",
    "PullPolicyRule",
    "SubmissionReceipt",
    "get_executor_adapter",
    "normalize_pull_policy_overrides",
    "register_executor_adapter",
    "resolve_pull_strategy",
    "suggest_merge",
    "suggest_split",
    "validate_granularity",
]
