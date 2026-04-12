from devforge.context import ContextBroker
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from devforge.executors import (
    PULL_POLICY_OVERRIDE_SCHEMA,
    ClaudeCodeAdapter,
    CodexAdapter,
    PythonAdapter,
    format_executor_payload,
    normalize_pull_policy_overrides,
    resolve_pull_strategy,
)
from devforge.executors.base import ClaudeCodeTaskRequest, CodexTaskRequest
from devforge.persistence import FileArtifactStore, JsonMemoryStore
from devforge.state import WorkPackage


def test_claude_code_payload_uses_design_heavy_shape() -> None:
    payload = format_executor_payload(
        "claude_code",
        {
            "node_knowledge_packet": {
                "brief": "implement backend flow",
                "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "backend"},
                "constraints": ["do not change seam"],
                "acceptance": ["tests pass"],
                "deep_refs": ["domain.ecommerce"],
            }
        },
    )
    assert payload["style"] == "design_heavy"
    assert payload["brief"] == "implement backend flow"
    assert payload["references"] == ["domain.ecommerce"]
    assert payload["result_contract"]["format"] == "json"


def test_claude_code_architect_payload_is_architecture_heavy() -> None:
    payload = format_executor_payload(
        "claude_code",
        {
            "node_knowledge_packet": {
                "brief": "define service boundary",
                "focus": {"phase": "analysis_design", "role_id": "technical_architect", "domain": "backend"},
                "constraints": ["preserve contracts"],
                "acceptance": ["boundary documented"],
                "deep_refs": ["phase.analysis_design"],
            }
        },
    )
    assert payload["style"] == "architecture_heavy"
    assert payload["decision_axes"] == ["module_boundaries", "contracts", "integration_risks"]
    assert "summary" in payload["result_contract"]["required_keys"]


def test_codex_payload_uses_execution_heavy_shape() -> None:
    payload = format_executor_payload(
        "codex",
        {
            "node_knowledge_packet": {
                "brief": "implement frontend flow",
                "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "frontend"},
                "constraints": ["preserve contract"],
                "acceptance": ["ui works"],
                "deep_refs": ["phase.implementation"],
            }
        },
    )
    assert payload["style"] == "execution_heavy"
    assert payload["task"] == "implement frontend flow"
    assert payload["knowledge_refs"] == ["phase.implementation"]
    assert "findings" in payload["result_contract"]["optional_keys"]


def test_codex_qa_payload_is_qa_execution() -> None:
    payload = format_executor_payload(
        "codex",
        {
            "node_knowledge_packet": {
                "brief": "verify checkout flow",
                "focus": {"phase": "testing", "role_id": "qa_engineer", "domain": "frontend"},
                "constraints": ["do not change contract"],
                "acceptance": ["checkout works end to end"],
                "deep_refs": ["phase.testing"],
            }
        },
    )
    assert payload["style"] == "qa_execution"
    assert payload["bug_focus"] == ["edge_cases", "regression", "contract_mismatches"]
    assert payload["result_contract"]["finding_shape"]["id"] == "string"


def test_codex_adapter_prepares_typed_request_before_submission() -> None:
    adapter = CodexAdapter()
    work_package = WorkPackage(
        work_package_id="wp-1",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="frontend",
        role_id="software_engineer",
        title="implement frontend",
        goal="implement frontend flow",
        status="ready",
        deliverables=["web/src/**"],
    )
    runtime_context = {
        "cycle_id": "cycle-0099",
        "node_knowledge_packet": {
            "brief": "implement frontend flow",
            "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "frontend"},
            "constraints": ["preserve contract"],
            "acceptance": ["ui works"],
            "deep_refs": ["phase.implementation"],
        }
    }

    request = adapter.prepare_request(work_package, runtime_context)
    dispatch = adapter.dispatch(work_package, runtime_context)

    assert isinstance(request, CodexTaskRequest)
    assert request.mode == "task_payload"
    assert request.cycle_id == "cycle-0099"
    assert request.deliverables == ["web/src/**"]
    assert dispatch.metadata["executor_request"]["mode"] == "task_payload"
    assert dispatch.metadata["executor_request"]["cycle_id"] == "cycle-0099"
    assert dispatch.metadata["cycle_id"] == "cycle-0099"
    assert dispatch.metadata["execution_ref"] == {
        "cycle_id": "cycle-0099",
        "work_package_id": "wp-1",
        "executor": "codex",
        "execution_id": "codex:wp-1",
    }
    assert dispatch.metadata["submit_boundary"] == "codex.submit_request"
    assert dispatch.metadata["submission_receipt"]["metadata"]["transport"] == "stub"


def test_claude_code_adapter_prepares_typed_request_before_submission() -> None:
    adapter = ClaudeCodeAdapter()
    work_package = WorkPackage(
        work_package_id="wp-2",
        initiative_id="i1",
        project_id="p1",
        phase="analysis_design",
        domain="backend",
        role_id="technical_architect",
        title="define service boundary",
        goal="define service boundary",
        status="ready",
    )
    runtime_context = {
        "cycle_id": "cycle-0100",
        "node_knowledge_packet": {
            "brief": "define service boundary",
            "focus": {"phase": "analysis_design", "role_id": "technical_architect", "domain": "backend"},
            "constraints": ["preserve contracts"],
            "acceptance": ["boundary documented"],
            "deep_refs": ["phase.analysis_design"],
        }
    }

    request = adapter.prepare_request(work_package, runtime_context)
    dispatch = adapter.dispatch(work_package, runtime_context)

    assert isinstance(request, ClaudeCodeTaskRequest)
    assert request.mode == "delegated_session"
    assert request.cycle_id == "cycle-0100"
    assert request.references == ["phase.analysis_design"]
    assert dispatch.metadata["executor_request"]["task_type"] == "architect_or_builder"
    assert dispatch.metadata["cycle_id"] == "cycle-0100"
    assert dispatch.metadata["execution_ref"]["cycle_id"] == "cycle-0100"
    assert dispatch.metadata["submit_boundary"] == "claude_code.submit_request"
    assert dispatch.metadata["submission_receipt"]["accepted"] is True


def test_dispatch_rejects_unsupported_work_even_if_transport_accepts_submission() -> None:
    adapter = CodexAdapter()
    work_package = WorkPackage(
        work_package_id="wp-3",
        initiative_id="i1",
        project_id="p1",
        phase="concept_collect",
        domain="product",
        role_id="product_manager",
        title="collect concept",
        goal="collect concept",
        status="ready",
    )

    dispatch = adapter.dispatch(work_package, {"node_knowledge_packet": {}})

    assert dispatch.accepted is False
    assert dispatch.message == "codex request rejected"
    assert dispatch.metadata["submission_receipt"]["accepted"] is True


def test_adapter_normalize_result_preserves_rich_fields() -> None:
    adapter = CodexAdapter()
    result = adapter.normalize_result(
        {
            "execution_id": "codex:wp-1",
            "work_package_id": "wp-1",
            "cycle_id": "cycle-0042",
            "status": "completed",
            "summary": "implemented flow",
            "artifacts_created": ["src/cart.py"],
            "artifacts_modified": ["src/api.py"],
            "tests_run": ["pytest tests/test_cart.py"],
            "findings": [
                {
                    "id": "f1",
                    "summary": "edge case remains",
                    "severity": "medium",
                    "source": "qa",
                }
            ],
            "handoff_notes": ["verify checkout seam"],
            "raw_output_ref": "run://codex/wp-1",
            "started_at": "2026-04-02T10:00:00Z",
            "completed_at": "2026-04-02T10:02:00Z",
        }
    )

    assert result.artifacts_created == ["src/cart.py"]
    assert result.artifacts_modified == ["src/api.py"]
    assert result.cycle_id == "cycle-0042"
    assert result.execution_ref == {
        "cycle_id": "cycle-0042",
        "work_package_id": "wp-1",
        "executor": "codex",
        "execution_id": "codex:wp-1",
    }
    assert result.tests_run == ["pytest tests/test_cart.py"]
    assert result.findings[0].id == "f1"
    assert result.handoff_notes == ["verify checkout seam"]
    assert result.raw_output_ref == "run://codex/wp-1"


def test_codex_adapter_can_return_subprocess_final_result(monkeypatch) -> None:
    adapter = CodexAdapter()
    work_package = WorkPackage(
        work_package_id="wp-live",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="core",
        role_id="software_engineer",
        title="live run",
        goal="run live",
        status="ready",
    )
    runtime_context = {
        "cycle_id": "cycle-live",
        "working_dir": "/tmp/project",
        "node_knowledge_packet": {
            "brief": "run live",
            "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "core"},
            "constraints": [],
            "acceptance": [],
            "deep_refs": ["phase.implementation"],
        },
    }
    monkeypatch.setenv("DEVFORGE_EXECUTOR_TRANSPORT", "subprocess")

    with patch.object(
        adapter,
        "_run_subprocess_request",
        return_value={
            "execution_id": "exec-live",
            "work_package_id": "wp-live",
            "cycle_id": "cycle-live",
            "status": "completed",
            "summary": "real executor output",
            "findings": [],
        },
    ):
        dispatch = adapter.dispatch(work_package, runtime_context)

    assert dispatch.accepted is True
    assert dispatch.metadata["submission_receipt"]["metadata"]["transport"] == "subprocess"
    assert dispatch.metadata["submission_receipt"]["metadata"]["final_result"]["summary"] == "real executor output"


def test_python_adapter_includes_deliverables_for_local_acceptance() -> None:
    adapter = PythonAdapter()
    work_package = WorkPackage(
        work_package_id="wp-accept",
        initiative_id="i1",
        project_id="p1",
        phase="acceptance",
        domain="core",
        role_id="integration_owner",
        title="close acceptance",
        goal="write acceptance report",
        status="ready",
        deliverables=["docs/devforge/bootstrap-acceptance.md"],
    )
    runtime_context = {
        "cycle_id": "cycle-0200",
        "node_knowledge_packet": {
            "brief": "close acceptance",
            "focus": {"phase": "acceptance", "role_id": "integration_owner", "domain": "core"},
            "acceptance": ["report blockers"],
            "incoming_handoff_notes": ["network unavailable"],
        },
    }

    request = adapter.prepare_request(work_package, runtime_context)

    assert request["cycle_id"] == "cycle-0200"
    assert request["goal"] == "write acceptance report"
    assert request["deliverables"] == ["docs/devforge/bootstrap-acceptance.md"]


def test_parse_subprocess_output_extracts_structured_result_fields() -> None:
    adapter = CodexAdapter()

    parsed = adapter._parse_subprocess_output(
        json.dumps(
            {
                "summary": "implemented feature",
                "artifacts_created": ["src/devforge/repl.py"],
                "artifacts_modified": ["README.md"],
                "tests_run": ["pytest -q tests/test_repl.py"],
                "handoff_notes": ["verify startup flow"],
                "findings": [
                    {
                        "id": "f-live-1",
                        "summary": "manual verification still needed",
                        "severity": "medium",
                        "source": "executor",
                    }
                ],
                "raw_output_ref": "stdout://codex",
            }
        )
    )

    assert parsed["summary"] == "implemented feature"
    assert parsed["artifacts_created"] == ["src/devforge/repl.py"]
    assert parsed["tests_run"] == ["pytest -q tests/test_repl.py"]
    assert parsed["handoff_notes"] == ["verify startup flow"]
    assert parsed["findings"][0]["id"] == "f-live-1"


def test_adapter_pull_context_uses_shared_broker(tmp_path) -> None:
    adapter = CodexAdapter()
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    memory_store = JsonMemoryStore(tmp_path / "memory")
    artifact_store.write_text("runtime/p1/concept_brief.md", "# Concept Brief\nhello")
    memory_store.save_memory(
        "project/p1",
        "latest-specialized-knowledge",
        '{"focus":["ecommerce"]}',
        metadata={"kind": "specialized_knowledge"},
    )
    broker = ContextBroker(
        snapshot={"projects": [{"project_id": "p1", "name": "Demo", "project_archetype": "ecommerce", "current_phase": "implementation", "domains": ["frontend"]}]},
        artifact_store=artifact_store,
        memory_store=memory_store,
    )

    bundle = adapter.pull_context(
        [
            "project://p1",
            "artifact://runtime/p1/concept_brief.md",
            "memory://project/p1/latest-specialized-knowledge",
        ],
        broker=broker,
        mode="summary",
        budget=120,
    )

    assert [item.kind for item in bundle] == ["project", "artifact", "memory"]
    assert "Demo" in bundle[0].content
    assert "Concept Brief" in bundle[1].content


def test_default_pull_strategy_differs_between_claude_code_and_codex() -> None:
    manifest = {
        "refs": [
            "project://p1",
            "artifact://runtime/p1/acceptance_goals.json",
            "memory://project/p1/latest-specialized-knowledge",
            "knowledge://domain.ecommerce",
        ]
    }
    work_package = WorkPackage(
        work_package_id="wp-1",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="frontend",
        role_id="software_engineer",
        title="implement",
        goal="implement",
        status="ready",
    )

    claude_strategy = ClaudeCodeAdapter().default_pull_strategy(work_package, {"context_pull_manifest": manifest})
    codex_strategy = CodexAdapter().default_pull_strategy(work_package, {"context_pull_manifest": manifest})

    assert claude_strategy["mode"] == "summary"
    assert "project://p1" in claude_strategy["refs"]
    assert "memory://project/p1/latest-specialized-knowledge" in claude_strategy["refs"]
    assert codex_strategy["mode"] == "structured"
    assert "project://p1" in codex_strategy["refs"]
    assert "memory://project/p1/latest-specialized-knowledge" in codex_strategy["refs"]


def test_default_pull_strategy_changes_with_role() -> None:
    manifest = {
        "refs": [
            "project://p1",
            "artifact://runtime/p1/concept_brief.md",
            "artifact://runtime/p1/acceptance_goals.json",
            "memory://project/p1/latest-specialized-knowledge",
            "knowledge://phase.analysis_design",
            "knowledge://phase.testing",
        ]
    }
    architect_wp = WorkPackage(
        work_package_id="wp-arch",
        initiative_id="i1",
        project_id="p1",
        phase="analysis_design",
        domain="backend",
        role_id="technical_architect",
        title="arch",
        goal="arch",
        status="ready",
    )
    qa_wp = WorkPackage(
        work_package_id="wp-qa",
        initiative_id="i1",
        project_id="p1",
        phase="testing",
        domain="frontend",
        role_id="qa_engineer",
        title="qa",
        goal="qa",
        status="ready",
    )

    claude_arch = ClaudeCodeAdapter().default_pull_strategy(architect_wp, {"context_pull_manifest": manifest})
    claude_qa = ClaudeCodeAdapter().default_pull_strategy(qa_wp, {"context_pull_manifest": manifest})
    codex_arch = CodexAdapter().default_pull_strategy(architect_wp, {"context_pull_manifest": manifest})
    codex_qa = CodexAdapter().default_pull_strategy(qa_wp, {"context_pull_manifest": manifest})

    assert "knowledge://phase.analysis_design" in claude_arch["refs"]
    assert "artifact://runtime/p1/acceptance_goals.json" in claude_qa["refs"]
    assert "knowledge://phase.analysis_design" in codex_arch["refs"]
    assert "artifact://runtime/p1/acceptance_goals.json" in codex_qa["refs"]
    assert "knowledge://phase.testing" in codex_qa["refs"]


def test_default_pull_strategy_changes_with_phase_for_software_engineer() -> None:
    manifest = {
        "refs": [
            "project://p1",
            "artifact://runtime/p1/concept_brief.md",
            "artifact://runtime/p1/acceptance_goals.json",
            "memory://project/p1/latest-specialized-knowledge",
            "knowledge://phase.implementation",
            "knowledge://phase.testing",
        ]
    }
    implementation_wp = WorkPackage(
        work_package_id="wp-impl",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="frontend",
        role_id="software_engineer",
        title="impl",
        goal="impl",
        status="ready",
    )
    testing_wp = WorkPackage(
        work_package_id="wp-test",
        initiative_id="i1",
        project_id="p1",
        phase="testing",
        domain="frontend",
        role_id="software_engineer",
        title="test",
        goal="test",
        status="ready",
    )

    claude_impl = ClaudeCodeAdapter().default_pull_strategy(implementation_wp, {"context_pull_manifest": manifest})
    claude_test = ClaudeCodeAdapter().default_pull_strategy(testing_wp, {"context_pull_manifest": manifest})
    codex_impl = CodexAdapter().default_pull_strategy(implementation_wp, {"context_pull_manifest": manifest})
    codex_test = CodexAdapter().default_pull_strategy(testing_wp, {"context_pull_manifest": manifest})

    assert "knowledge://phase.implementation" in claude_impl["refs"]
    assert "artifact://runtime/p1/acceptance_goals.json" in claude_test["refs"]
    assert "knowledge://phase.implementation" in codex_impl["refs"]
    assert "artifact://runtime/p1/acceptance_goals.json" in codex_test["refs"]
    assert "knowledge://phase.testing" in codex_test["refs"]


def test_resolve_pull_strategy_uses_registry_rules() -> None:
    refs = [
        "project://p1",
        "artifact://runtime/p1/acceptance_goals.json",
        "memory://project/p1/latest-specialized-knowledge",
        "knowledge://phase.testing",
    ]
    work_package = WorkPackage(
        work_package_id="wp-qa",
        initiative_id="i1",
        project_id="p1",
        phase="testing",
        domain="frontend",
        role_id="qa_engineer",
        title="qa",
        goal="qa",
        status="ready",
    )

    strategy = resolve_pull_strategy("codex", work_package, refs)

    assert strategy["mode"] == "structured"
    assert "project://p1" in strategy["refs"]
    assert "artifact://runtime/p1/acceptance_goals.json" in strategy["refs"]
    assert "knowledge://phase.testing" in strategy["refs"]


def test_resolve_pull_strategy_can_match_project_archetype() -> None:
    refs = [
        "project://p1",
        "memory://project/p1/latest-specialized-knowledge",
        "knowledge://phase.implementation",
        "knowledge://domain.gaming",
    ]
    work_package = WorkPackage(
        work_package_id="wp-game",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="gameplay",
        role_id="software_engineer",
        title="game impl",
        goal="game impl",
        status="ready",
    )

    strategy = resolve_pull_strategy("codex", work_package, refs, project_archetype="game")

    assert strategy["mode"] == "structured"
    assert "knowledge://domain.gaming" in strategy["refs"]


def test_resolve_pull_strategy_allows_project_override_rules() -> None:
    refs = [
        "project://p1",
        "artifact://runtime/p1/concept_brief.md",
        "knowledge://domain.ecommerce",
    ]
    work_package = WorkPackage(
        work_package_id="wp-custom",
        initiative_id="i1",
        project_id="p1",
        phase="implementation",
        domain="frontend",
        role_id="software_engineer",
        title="custom",
        goal="custom",
        status="ready",
    )

    strategy = resolve_pull_strategy(
        "codex",
        work_package,
        refs,
        project_archetype="ecommerce",
        override_rules=[
            {
                "executor": "codex",
                "role_id": "software_engineer",
                "phase": "implementation",
                "mode": "summary",
                "budget": 333,
                "ref_patterns": ["concept_brief.md"],
            }
        ],
    )

    assert strategy["mode"] == "summary"
    assert strategy["budget"] == 333
    assert strategy["refs"] == ["artifact://runtime/p1/concept_brief.md"]


def test_normalize_pull_policy_overrides_validates_required_fields() -> None:
    with pytest.raises(ValueError):
        normalize_pull_policy_overrides([{"executor": "codex"}])

    with pytest.raises(ValueError):
        normalize_pull_policy_overrides([{"executor": "codex", "mode": "weird"}])


def test_pull_policy_override_schema_and_example_fixture_are_consistent() -> None:
    assert PULL_POLICY_OVERRIDE_SCHEMA["required"] == ["executor", "mode"]
    example_path = Path(__file__).resolve().parents[1] / "src" / "devforge" / "fixtures" / "pull_policy_overrides.example.json"
    data = json.loads(example_path.read_text(encoding="utf-8"))
    rules = normalize_pull_policy_overrides(data["pull_policy_overrides"])

    assert len(rules) == 2
    assert rules[0].project_archetype == "ecommerce"
    assert rules[1].role_id == "qa_engineer"
