from devforge.planning import resolve_retry_action


def test_retry_policy_returns_final_fail_when_attempt_limit_reached() -> None:
    action = resolve_retry_action(
        {"attempt_count": 3, "max_attempts": 3, "fallback_executors": []},
        {"summary": "executor rejected unsupported work package", "execution_ref": {"executor": "python"}},
    )

    assert action == {"action": "final_fail", "reason": "attempt_limit_reached"}


def test_retry_policy_switches_executor_on_rejected_work_when_fallback_exists() -> None:
    action = resolve_retry_action(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["codex", "claude_code"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
    )

    assert action == {
        "action": "switch_executor",
        "reason": "unsupported_by_executor",
        "next_executor": "codex",
    }


def test_retry_policy_requeues_when_retry_allowed_without_executor_switch() -> None:
    action = resolve_retry_action(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": []},
        {"summary": "transient failure", "execution_ref": {"executor": "codex"}},
    )

    assert action == {"action": "requeue", "reason": "retry_allowed"}


def test_retry_policy_blocks_on_seam_or_contract_failure() -> None:
    action = resolve_retry_action(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": []},
        {"summary": "contract mismatch detected", "execution_ref": {"executor": "codex"}},
    )

    assert action == {"action": "block", "reason": "seam_or_contract_issue"}


def test_retry_policy_requests_replan_when_requirement_context_changed() -> None:
    action = resolve_retry_action(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["codex"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
        context={"requirement_patch_applied": True},
    )

    assert action == {"action": "replan", "reason": "requirement_context_changed"}
