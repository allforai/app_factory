from devforge.planning import build_retry_guardrail, decide_retry_action, llm_retry_decider


def test_retry_guardrail_forbids_executor_switch_after_requirement_patch() -> None:
    guardrail = build_retry_guardrail(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["codex"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
        context={"requirement_patch_applied": True},
    )

    assert "switch_executor" in guardrail.forbidden_actions
    assert "requeue" in guardrail.forbidden_actions


def test_llm_retry_decider_returns_structured_semantic_decision() -> None:
    decision = llm_retry_decider(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["codex"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
        context={
            "requirement_patch_applied": True,
            "specialized_knowledge": {"focus": ["game", "implementation", "combat"]},
            "node_knowledge_packet": {"focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "gameplay"}},
            "related_seams": [],
            "requirement_events": [{"requirement_event_id": "req-1"}],
        },
    )

    assert decision.source == "mock:mock-structured-v1"
    assert decision.confidence == 0.72
    assert decision.notes


def test_decide_retry_action_falls_back_to_guardrail_when_semantic_action_is_forbidden() -> None:
    decision = decide_retry_action(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["codex"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
        context={"requirement_patch_applied": True},
    )

    assert decision.source == "mock:mock-structured-v1"
    assert decision.action == "replan"


def test_llm_retry_decider_uses_richer_context_to_block_on_unstable_seam() -> None:
    decision = llm_retry_decider(
        {
            "attempt_count": 1,
            "max_attempts": 3,
            "fallback_executors": ["claude_code"],
            "execution_history": [{"execution_id": "codex:wp-1"}, {"execution_id": "codex:wp-2"}],
        },
        {"summary": "integration seam mismatch", "execution_ref": {"executor": "codex"}},
        context={
            "requirement_patch_applied": False,
            "related_seams": [{"seam_id": "s1", "status": "draft"}],
            "specialized_knowledge": {"focus": ["ecommerce", "integration"]},
            "node_knowledge_packet": {"focus": {"phase": "testing", "role_id": "qa_engineer", "domain": "integration"}},
            "requirement_events": [],
        },
    )

    assert decision.action == "block"
    assert decision.reason == "seam_not_stable"
