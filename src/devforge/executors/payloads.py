"""Executor-specific payload formatting for node knowledge packets."""

from __future__ import annotations

from typing import Any


def _result_contract() -> dict[str, Any]:
    return {
        "format": "json",
        "required_keys": ["summary"],
        "optional_keys": [
            "artifacts_created",
            "artifacts_modified",
            "tests_run",
            "findings",
            "handoff_notes",
            "raw_output_ref",
        ],
        "finding_shape": {
            "id": "string",
            "summary": "string",
            "severity": "string",
            "source": "string",
            "details": "string?",
            "related_artifacts": ["string"],
        },
    }


def format_executor_payload(executor_name: str, runtime_context: dict[str, Any]) -> dict[str, Any]:
    """Format runtime context into an executor-specific payload."""
    packet = runtime_context.get("node_knowledge_packet", {})
    focus = packet.get("focus", {})
    role_id = focus.get("role_id")
    pull_manifest = runtime_context.get("context_pull_manifest", {})

    if executor_name == "claude_code":
        if role_id == "technical_architect":
            return {
                "style": "architecture_heavy",
                "brief": packet.get("brief", ""),
                "focus": focus,
                "constraints": packet.get("constraints", []),
                "decision_axes": ["module_boundaries", "contracts", "integration_risks"],
                "acceptance": packet.get("acceptance", []),
                "references": packet.get("deep_refs", []),
                "pull_manifest": pull_manifest,
                "result_contract": _result_contract(),
            }
        if role_id == "qa_engineer":
            return {
                "style": "verification_heavy",
                "brief": packet.get("brief", ""),
                "focus": focus,
                "checks": packet.get("acceptance", []),
                "risk_focus": ["regression", "edge_cases", "seams"],
                "references": packet.get("deep_refs", []),
                "pull_manifest": pull_manifest,
                "result_contract": _result_contract(),
            }
        return {
            "style": "design_heavy",
            "brief": packet.get("brief", ""),
            "focus": focus,
            "constraints": packet.get("constraints", []),
            "acceptance": packet.get("acceptance", []),
            "references": packet.get("deep_refs", []),
            "pull_manifest": pull_manifest,
            "result_contract": _result_contract(),
        }

    if executor_name == "codex":
        if role_id == "qa_engineer":
            return {
                "style": "qa_execution",
                "task": packet.get("brief", ""),
                "checks": packet.get("acceptance", []),
                "bug_focus": ["edge_cases", "regression", "contract_mismatches"],
                "knowledge_refs": packet.get("deep_refs", []),
                "focus_summary": focus,
                "pull_manifest": pull_manifest,
                "result_contract": _result_contract(),
            }
        if role_id == "technical_architect":
            return {
                "style": "implementation_with_architecture_guardrails",
                "task": packet.get("brief", ""),
                "rules": packet.get("constraints", []),
                "architecture_focus": ["boundaries", "contracts", "shared_abstractions"],
                "knowledge_refs": packet.get("deep_refs", []),
                "focus_summary": focus,
                "pull_manifest": pull_manifest,
                "result_contract": _result_contract(),
            }
        return {
            "style": "execution_heavy",
            "task": packet.get("brief", ""),
            "rules": packet.get("constraints", []),
            "checks": packet.get("acceptance", []),
            "knowledge_refs": packet.get("deep_refs", []),
            "focus_summary": focus,
            "pull_manifest": pull_manifest,
            "result_contract": _result_contract(),
        }

    return {
        "style": "generic",
        "runtime_context": runtime_context,
    }
