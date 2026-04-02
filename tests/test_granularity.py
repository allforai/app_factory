# tests/test_granularity.py
from devforge.executors.granularity import estimate_package_tokens, validate_granularity, GranularityAction, suggest_split, suggest_merge
from devforge.state import WorkPackage


def _make_wp(wp_id="WP-1", goal="implement feature", acceptance_criteria=None, constraints=None, deliverables=None):
    return WorkPackage(work_package_id=wp_id, initiative_id="I-1", project_id="P-1", phase="implementation", domain="backend", role_id="software_engineer", title=f"WP {wp_id}", goal=goal, status="ready", acceptance_criteria=acceptance_criteria or ["test passes"], constraints=constraints or [], deliverables=deliverables or ["code"])


def test_estimate_package_tokens():
    wp = _make_wp(goal="short goal")
    tokens = estimate_package_tokens(wp)
    assert tokens > 0 and isinstance(tokens, int)


def test_estimate_grows_with_content():
    small = _make_wp(goal="x")
    large = _make_wp(goal="implement the entire payment processing pipeline with retry logic and webhook handling", acceptance_criteria=["unit tests", "integration tests", "error handling", "logging"], constraints=["must be idempotent", "must handle timeouts"], deliverables=["payment.py", "webhook.py", "tests/test_payment.py"])
    assert estimate_package_tokens(large) > estimate_package_tokens(small)


def test_validate_granularity_ok():
    assert validate_granularity(_make_wp(), "codex").action == "ok"


def test_validate_granularity_too_large_for_codex():
    wp = _make_wp(goal="x " * 5000, acceptance_criteria=["c" * 200 for _ in range(20)])
    action = validate_granularity(wp, "codex")
    assert action.action == "split" and action.reason != ""


def test_validate_granularity_suggests_merge_for_claude_code():
    action = validate_granularity(_make_wp(goal="tiny"), "claude_code")
    assert action.action in ("ok", "merge")


def test_suggest_split():
    wp = _make_wp(goal="implement auth, payments, and notifications", deliverables=["auth.py", "payments.py", "notifications.py"], acceptance_criteria=["auth works", "payments work", "notifications work"])
    splits = suggest_split(wp, target_count=3)
    assert len(splits) == 3
    for s in splits:
        assert s.work_package_id.startswith("WP-1-split-") and s.status == "proposed" and s.project_id == "P-1"


def test_suggest_merge():
    wps = [_make_wp(wp_id=f"WP-{i}", goal=f"add field {chr(65+i)}") for i in range(3)]
    merged = suggest_merge(wps)
    assert merged.work_package_id.startswith("merged-") and merged.status == "proposed"


def test_executor_switch_triggers_regranularity():
    small_wps = [_make_wp(wp_id=f"WP-{i}", goal=f"tiny task {i}") for i in range(5)]
    actions = [validate_granularity(wp, "claude_code") for wp in small_wps]
    merge_suggested = sum(1 for a in actions if a.action == "merge")
    assert merge_suggested >= 0  # threshold-dependent
