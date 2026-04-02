# Plan 3: 集成缝合与产品验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement seam contract verification, LLM-driven product-level acceptance with role-specific evaluation, and gap analysis with precise attribution back to capability domains — completing the verification loop that makes the engine converge toward production-grade output.

**Architecture:** Three new modules: (1) `seams/verifier.py` — compare executor outputs against frozen seam contracts to detect drift; (2) `planning/acceptance.py` — LLM-driven acceptance evaluator that walks user flows per role, scores closure density, and produces a production-ready verdict; (3) `planning/gap_analyzer.py` — map gaps to capability domains (#1-#17) and generate remediation work packages. These plug into a new `acceptance_and_gap_check_node` in the graph.

**Tech Stack:** Python 3.12, dataclasses, existing LLM client protocol (mock for TDD), pytest.

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `src/devforge/seams/verifier.py` | Compare implementation artifacts against frozen seam contracts |
| Create: `src/devforge/planning/acceptance.py` | LLM-driven product-level acceptance evaluation |
| Create: `src/devforge/planning/gap_analyzer.py` | Gap attribution to capability domains + remediation package generation |
| Create: `src/devforge/state/acceptance.py` | Acceptance verdict and gap data models |
| Modify: `src/devforge/graph/nodes.py` | Add acceptance_and_gap_check_node |
| Modify: `src/devforge/graph/runtime_state.py` | Add acceptance_verdict field |
| Modify: `src/devforge/llm/mock.py` | Add mock responses for acceptance and gap_analysis tasks |
| Create: `tests/test_seam_verifier.py` | Tests for seam contract verification |
| Create: `tests/test_acceptance.py` | Tests for acceptance evaluation |
| Create: `tests/test_gap_analyzer.py` | Tests for gap attribution and remediation |
| Create: `tests/test_acceptance_integration.py` | Integration test: results → seam check → acceptance → gap → remediation |

---

### Task 1: Acceptance and Gap Data Models

**Files:**
- Create: `src/devforge/state/acceptance.py`
- Modify: `src/devforge/state/__init__.py`
- Test: `tests/test_acceptance_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_acceptance_model.py
"""Tests for acceptance verdict and gap data models."""

from devforge.state.acceptance import (
    AcceptanceVerdict,
    GoalCheckResult,
    GapItem,
    ClosureDensityScore,
    RemediationPackage,
)


def test_acceptance_verdict_production_ready():
    verdict = AcceptanceVerdict(
        verdict_id="V-001",
        project_id="P-1",
        cycle_id="cycle-0005",
        is_production_ready=True,
        overall_score=0.95,
        goal_checks=[
            GoalCheckResult(goal="用户能完成购买", status="met", reason="核心购买流程完整"),
        ],
        gaps=[],
        closure_density=ClosureDensityScore(
            total_ring_0=10, covered=9, coverage_ratio=0.9,
        ),
        role_evaluations={"buyer": "流程完整", "admin": "管理功能齐全"},
        summary="达到生产级别",
    )
    assert verdict.is_production_ready is True
    assert verdict.overall_score == 0.95
    assert len(verdict.goal_checks) == 1
    assert verdict.closure_density.coverage_ratio == 0.9


def test_gap_item():
    gap = GapItem(
        gap_id="G-001",
        description="支付流程缺少异常处理",
        severity="high",
        attributed_domain="#2",
        attributed_capability="产品设计",
        remediation_target="design",
    )
    assert gap.attributed_domain == "#2"
    assert gap.remediation_target == "design"


def test_remediation_package():
    pkg = RemediationPackage(
        remediation_id="R-001",
        gap_id="G-001",
        action="redesign",
        target_phase="analysis_design",
        description="重新设计支付异常处理流程",
        affected_work_packages=["WP-payment"],
    )
    assert pkg.action == "redesign"
    assert "WP-payment" in pkg.affected_work_packages


def test_goal_check_statuses():
    for status in ("met", "partial", "unmet"):
        check = GoalCheckResult(goal="test", status=status, reason="test")
        assert check.status == status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance_model.py -v`
Expected: FAIL

- [ ] **Step 3: Implement acceptance data models**

```python
# src/devforge/state/acceptance.py
"""Acceptance verdict and gap analysis data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class GoalCheckResult:
    """One acceptance goal evaluated against deliverables."""

    goal: str
    status: Literal["met", "partial", "unmet"]
    reason: str


@dataclass(slots=True)
class ClosureDensityScore:
    """How many Ring 0 tasks have complete closure coverage."""

    total_ring_0: int
    covered: int
    coverage_ratio: float


@dataclass(slots=True)
class GapItem:
    """One identified gap from acceptance evaluation."""

    gap_id: str
    description: str
    severity: Literal["high", "medium", "low"]
    attributed_domain: str
    attributed_capability: str
    remediation_target: Literal["design", "decomposition", "implementation", "testing"]


@dataclass(slots=True)
class RemediationPackage:
    """A proposed work package to close a gap."""

    remediation_id: str
    gap_id: str
    action: Literal["redesign", "reimplement", "add_test", "add_feature", "fix_seam"]
    target_phase: str
    description: str
    affected_work_packages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AcceptanceVerdict:
    """Complete acceptance evaluation result."""

    verdict_id: str
    project_id: str
    cycle_id: str
    is_production_ready: bool
    overall_score: float
    goal_checks: list[GoalCheckResult] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    closure_density: ClosureDensityScore | None = None
    role_evaluations: dict[str, str] = field(default_factory=dict)
    remediations: list[RemediationPackage] = field(default_factory=list)
    summary: str = ""
```

- [ ] **Step 4: Update state __init__.py**

Add exports for the new types.

- [ ] **Step 5: Run tests**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance_model.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/devforge/state/acceptance.py src/devforge/state/__init__.py tests/test_acceptance_model.py
git commit -m "feat: add acceptance verdict and gap analysis data models"
```

---

### Task 2: Seam Contract Verifier

**Files:**
- Create: `src/devforge/seams/verifier.py`
- Test: `tests/test_seam_verifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seam_verifier.py
"""Tests for seam contract verification."""

from devforge.seams.verifier import (
    verify_seam_compliance,
    SeamComplianceResult,
    SeamViolation,
)


def _make_seam(seam_id="S-1", status="frozen", acceptance_criteria=None, artifacts=None):
    return {
        "seam_id": seam_id,
        "status": status,
        "acceptance_criteria": acceptance_criteria or ["API returns JSON", "status codes are 2xx/4xx"],
        "artifacts": artifacts or ["api-contract.json"],
        "contract_version": "v1",
        "source_project_id": "P-A",
        "target_project_id": "P-B",
    }


def test_frozen_seam_with_matching_results_passes():
    seam = _make_seam()
    wp_results = [
        {"work_package_id": "WP-1", "status": "completed", "summary": "API implemented, returns JSON with proper status codes"},
    ]
    result = verify_seam_compliance(seam, wp_results)
    assert result.compliant is True
    assert len(result.violations) == 0


def test_frozen_seam_with_no_results_fails():
    seam = _make_seam()
    result = verify_seam_compliance(seam, [])
    assert result.compliant is False
    assert any(v.violation_type == "no_implementation" for v in result.violations)


def test_broken_status_when_result_mentions_deviation():
    seam = _make_seam()
    wp_results = [
        {"work_package_id": "WP-1", "status": "completed", "summary": "API returns XML instead of JSON, deviation from contract"},
    ]
    result = verify_seam_compliance(seam, wp_results)
    assert result.compliant is False
    assert any(v.violation_type == "contract_deviation" for v in result.violations)


def test_non_frozen_seam_skipped():
    seam = _make_seam(status="draft")
    result = verify_seam_compliance(seam, [])
    assert result.compliant is True  # draft seams are not enforced
    assert result.skipped is True


def test_failed_result_means_seam_not_verified():
    seam = _make_seam()
    wp_results = [
        {"work_package_id": "WP-1", "status": "failed", "summary": "execution failed"},
    ]
    result = verify_seam_compliance(seam, wp_results)
    assert result.compliant is False
    assert any(v.violation_type == "implementation_failed" for v in result.violations)


def test_multiple_criteria_partial_compliance():
    seam = _make_seam(acceptance_criteria=["endpoint exists", "auth required", "rate limited"])
    wp_results = [
        {"work_package_id": "WP-1", "status": "completed", "summary": "endpoint implemented with auth, no rate limiting yet"},
    ]
    result = verify_seam_compliance(seam, wp_results)
    assert result.compliant is False
    assert result.criteria_met > 0
    assert result.criteria_met < len(seam["acceptance_criteria"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_seam_verifier.py -v`
Expected: FAIL

- [ ] **Step 3: Implement seam verifier**

```python
# src/devforge/seams/verifier.py
"""Verify executor outputs against frozen seam contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SeamViolation:
    """One specific seam contract violation."""

    violation_type: str  # "no_implementation", "contract_deviation", "implementation_failed", "criteria_unmet"
    description: str
    seam_id: str = ""
    work_package_id: str = ""


@dataclass(slots=True)
class SeamComplianceResult:
    """Result of seam compliance verification."""

    seam_id: str
    compliant: bool
    skipped: bool = False
    violations: list[SeamViolation] = field(default_factory=list)
    criteria_met: int = 0
    criteria_total: int = 0


_DEVIATION_KEYWORDS = ["deviation", "diverge", "mismatch", "incompatible", "instead of", "differs from", "broke", "breaking"]
_ENFORCEABLE_STATUSES = {"frozen", "implemented", "verified"}


def verify_seam_compliance(
    seam: dict[str, Any],
    wp_results: list[dict[str, Any]],
) -> SeamComplianceResult:
    """Check whether work package results satisfy a seam's contract."""
    seam_id = seam.get("seam_id", "")
    status = seam.get("status", "draft")
    criteria = seam.get("acceptance_criteria", [])

    if status not in _ENFORCEABLE_STATUSES:
        return SeamComplianceResult(seam_id=seam_id, compliant=True, skipped=True)

    violations: list[SeamViolation] = []

    if not wp_results:
        violations.append(SeamViolation(
            violation_type="no_implementation",
            description=f"Seam {seam_id} is {status} but has no related work package results",
            seam_id=seam_id,
        ))
        return SeamComplianceResult(
            seam_id=seam_id, compliant=False, violations=violations,
            criteria_total=len(criteria),
        )

    # Check for failed results
    for result in wp_results:
        if result.get("status") in ("failed", "timed_out"):
            violations.append(SeamViolation(
                violation_type="implementation_failed",
                description=f"Work package {result.get('work_package_id', '?')} failed: {result.get('summary', '')}",
                seam_id=seam_id,
                work_package_id=result.get("work_package_id", ""),
            ))

    # Check for contract deviations in summaries
    all_summaries = " ".join(r.get("summary", "") for r in wp_results).lower()
    for keyword in _DEVIATION_KEYWORDS:
        if keyword in all_summaries:
            violations.append(SeamViolation(
                violation_type="contract_deviation",
                description=f"Work package output mentions '{keyword}', suggesting contract drift",
                seam_id=seam_id,
            ))
            break

    # Check acceptance criteria coverage
    criteria_met = 0
    for criterion in criteria:
        criterion_lower = criterion.lower()
        # Simple keyword match: check if criterion's key terms appear in results
        key_terms = [t for t in criterion_lower.split() if len(t) > 3]
        if key_terms and any(term in all_summaries for term in key_terms):
            criteria_met += 1
        elif not key_terms:
            criteria_met += 1  # trivial criterion considered met

    if criteria_met < len(criteria) and not violations:
        unmet = len(criteria) - criteria_met
        violations.append(SeamViolation(
            violation_type="criteria_unmet",
            description=f"{unmet} of {len(criteria)} acceptance criteria not evidenced in results",
            seam_id=seam_id,
        ))

    return SeamComplianceResult(
        seam_id=seam_id,
        compliant=len(violations) == 0,
        violations=violations,
        criteria_met=criteria_met,
        criteria_total=len(criteria),
    )
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_seam_verifier.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/seams/verifier.py tests/test_seam_verifier.py
git commit -m "feat: add seam contract compliance verifier"
```

---

### Task 3: LLM-Driven Acceptance Evaluator

**Files:**
- Create: `src/devforge/planning/acceptance.py`
- Modify: `src/devforge/llm/mock.py`
- Test: `tests/test_acceptance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_acceptance.py
"""Tests for LLM-driven product-level acceptance evaluation."""

from devforge.planning.acceptance import evaluate_acceptance
from devforge.state.acceptance import AcceptanceVerdict
from devforge.llm import MockLLMClient


def test_evaluate_acceptance_returns_verdict():
    verdict = evaluate_acceptance(
        project_id="P-1",
        cycle_id="cycle-0005",
        acceptance_goals=["用户能完成购买流程", "管理员能审核订单"],
        work_package_results=[
            {"work_package_id": "WP-1", "status": "completed", "summary": "购买流程实现完整"},
            {"work_package_id": "WP-2", "status": "completed", "summary": "管理后台审核功能完成"},
        ],
        design_summary={"product_name": "电商平台", "ring_0_tasks": ["购买", "审核"], "domains": []},
        closure_expansion={"total_ring_0": 2, "total_ring_1": 6, "closures": []},
        llm_client=MockLLMClient(),
    )
    assert isinstance(verdict, AcceptanceVerdict)
    assert verdict.project_id == "P-1"
    assert len(verdict.goal_checks) > 0
    assert verdict.overall_score > 0


def test_evaluate_acceptance_with_failures_not_production_ready():
    verdict = evaluate_acceptance(
        project_id="P-1",
        cycle_id="cycle-0005",
        acceptance_goals=["用户能完成购买流程"],
        work_package_results=[
            {"work_package_id": "WP-1", "status": "failed", "summary": "支付模块未实现"},
        ],
        design_summary={"product_name": "电商平台", "ring_0_tasks": ["购买"]},
        closure_expansion={"total_ring_0": 1, "total_ring_1": 3, "closures": []},
        llm_client=MockLLMClient(),
    )
    assert verdict.is_production_ready is False
    assert len(verdict.gaps) > 0


def test_evaluate_acceptance_includes_role_evaluations():
    verdict = evaluate_acceptance(
        project_id="P-1",
        cycle_id="cycle-0005",
        acceptance_goals=["buyer can purchase", "admin can manage"],
        work_package_results=[
            {"work_package_id": "WP-1", "status": "completed", "summary": "all done"},
        ],
        design_summary={"product_name": "电商", "ring_0_tasks": ["购买"], "user_flows": [{"role": "buyer"}, {"role": "admin"}]},
        closure_expansion={"total_ring_0": 1, "total_ring_1": 3, "closures": []},
        llm_client=MockLLMClient(),
    )
    assert len(verdict.role_evaluations) > 0


def test_evaluate_acceptance_closure_density():
    verdict = evaluate_acceptance(
        project_id="P-1",
        cycle_id="cycle-0005",
        acceptance_goals=["feature complete"],
        work_package_results=[
            {"work_package_id": "WP-1", "status": "completed", "summary": "done"},
        ],
        design_summary={"product_name": "Test", "ring_0_tasks": ["task1", "task2"]},
        closure_expansion={"total_ring_0": 2, "total_ring_1": 6, "coverage_ratio": 0.85, "closures": []},
        llm_client=MockLLMClient(),
    )
    assert verdict.closure_density is not None
    assert verdict.closure_density.total_ring_0 == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance.py -v`
Expected: FAIL

- [ ] **Step 3: Add mock response for acceptance task**

In `src/devforge/llm/mock.py`, add handler for `request.task == "acceptance_evaluation"`:

```python
        if request.task == "acceptance_evaluation":
            output = self._acceptance_output(request)
            return StructuredGenerationResponse(
                output=output,
                provider=self.provider_name,
                model=self.model_name,
                raw_text=str(output),
                metadata={"task": request.task, "schema_name": request.schema_name},
            )
```

Add method:

```python
    def _acceptance_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        goals = payload.get("acceptance_goals", [])
        results = payload.get("work_package_results", [])
        design = payload.get("design_summary", {})
        closure = payload.get("closure_expansion", {})

        has_failures = any(r.get("status") in ("failed", "timed_out") for r in results)
        all_completed = all(r.get("status") in ("completed", "verified") for r in results) and results

        goal_checks = []
        for goal in goals:
            if has_failures:
                goal_checks.append({"goal": goal, "status": "unmet", "reason": "work packages have failures"})
            elif all_completed:
                goal_checks.append({"goal": goal, "status": "met", "reason": "all work packages completed"})
            else:
                goal_checks.append({"goal": goal, "status": "partial", "reason": "mixed results"})

        gaps = []
        if has_failures:
            gaps.append({
                "gap_id": "G-mock-1",
                "description": "Work package failures prevent acceptance",
                "severity": "high",
                "attributed_domain": "#11",
                "attributed_capability": "实现",
                "remediation_target": "implementation",
            })

        roles = [f.get("role", "user") for f in design.get("user_flows", [])]
        role_evaluations = {role: "evaluated" for role in roles} if roles else {"user": "evaluated"}

        ring_0 = closure.get("total_ring_0", 0)
        coverage = closure.get("coverage_ratio", 0.8)

        return {
            "is_production_ready": all_completed and not gaps,
            "overall_score": 0.95 if all_completed and not gaps else 0.4,
            "goal_checks": goal_checks,
            "gaps": gaps,
            "closure_density": {
                "total_ring_0": ring_0,
                "covered": int(ring_0 * coverage),
                "coverage_ratio": coverage,
            },
            "role_evaluations": role_evaluations,
            "summary": "达到生产级别" if all_completed and not gaps else "存在差距需要解决",
        }
```

- [ ] **Step 4: Implement acceptance evaluator**

```python
# src/devforge/planning/acceptance.py
"""LLM-driven product-level acceptance evaluation."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from devforge.llm import LLMClient, MockLLMClient, StructuredGenerationRequest, build_task_llm_client
from devforge.state.acceptance import (
    AcceptanceVerdict,
    ClosureDensityScore,
    GapItem,
    GoalCheckResult,
    RemediationPackage,
)


def evaluate_acceptance(
    *,
    project_id: str,
    cycle_id: str,
    acceptance_goals: list[str],
    work_package_results: list[dict[str, Any]],
    design_summary: dict[str, Any],
    closure_expansion: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> AcceptanceVerdict:
    """Evaluate whether project deliverables meet acceptance criteria."""
    llm_client = llm_client or build_task_llm_client(task="acceptance_evaluation", preferences=llm_preferences) or MockLLMClient()
    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="acceptance_evaluation",
            schema_name="AcceptanceVerdict",
            instructions=(
                "Evaluate whether the project deliverables meet acceptance goals. "
                "Walk through user flows per role. Check closure density. "
                "Identify gaps with precise attribution to capability domains. "
                "Output a production-ready verdict."
            ),
            input_payload={
                "acceptance_goals": acceptance_goals,
                "work_package_results": work_package_results,
                "design_summary": design_summary,
                "closure_expansion": closure_expansion or {},
            },
            metadata={"decision_kind": "acceptance_evaluation"},
        )
    )
    output = response.output

    goal_checks = [
        GoalCheckResult(
            goal=gc.get("goal", ""),
            status=gc.get("status", "unmet"),
            reason=gc.get("reason", ""),
        )
        for gc in output.get("goal_checks", [])
    ]

    gaps = [
        GapItem(
            gap_id=g.get("gap_id", f"G-{uuid4().hex[:6]}"),
            description=g.get("description", ""),
            severity=g.get("severity", "medium"),
            attributed_domain=g.get("attributed_domain", ""),
            attributed_capability=g.get("attributed_capability", ""),
            remediation_target=g.get("remediation_target", "implementation"),
        )
        for g in output.get("gaps", [])
    ]

    cd = output.get("closure_density") or {}
    closure_density = ClosureDensityScore(
        total_ring_0=cd.get("total_ring_0", 0),
        covered=cd.get("covered", 0),
        coverage_ratio=cd.get("coverage_ratio", 0.0),
    ) if cd else None

    return AcceptanceVerdict(
        verdict_id=f"V-{uuid4().hex[:8]}",
        project_id=project_id,
        cycle_id=cycle_id,
        is_production_ready=bool(output.get("is_production_ready", False)),
        overall_score=float(output.get("overall_score", 0.0)),
        goal_checks=goal_checks,
        gaps=gaps,
        closure_density=closure_density,
        role_evaluations=dict(output.get("role_evaluations", {})),
        summary=str(output.get("summary", "")),
    )
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/devforge/planning/acceptance.py src/devforge/llm/mock.py tests/test_acceptance.py
git commit -m "feat: add LLM-driven acceptance evaluator with role and closure assessment"
```

---

### Task 4: Gap Analyzer

**Files:**
- Create: `src/devforge/planning/gap_analyzer.py`
- Test: `tests/test_gap_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gap_analyzer.py
"""Tests for gap attribution and remediation package generation."""

from devforge.planning.gap_analyzer import (
    analyze_gaps,
    generate_remediations,
    attribute_gap_to_domain,
)
from devforge.state.acceptance import GapItem, RemediationPackage


def test_attribute_design_gap():
    gap = GapItem(
        gap_id="G-1", description="缺少支付异常处理流程",
        severity="high", attributed_domain="", attributed_capability="",
        remediation_target="design",
    )
    attributed = attribute_gap_to_domain(gap)
    assert attributed.attributed_domain == "#2"
    assert attributed.attributed_capability == "产品设计"


def test_attribute_implementation_gap():
    gap = GapItem(
        gap_id="G-2", description="API endpoint返回错误格式",
        severity="medium", attributed_domain="", attributed_capability="",
        remediation_target="implementation",
    )
    attributed = attribute_gap_to_domain(gap)
    assert attributed.attributed_domain in ("#4", "#5", "#6")


def test_generate_remediations():
    gaps = [
        GapItem(gap_id="G-1", description="缺少退款流程", severity="high",
                attributed_domain="#2", attributed_capability="产品设计",
                remediation_target="design"),
        GapItem(gap_id="G-2", description="搜索排序不正确", severity="medium",
                attributed_domain="#4", attributed_capability="任务分解",
                remediation_target="implementation"),
    ]
    remediations = generate_remediations(gaps, project_id="P-1")
    assert len(remediations) == 2
    assert remediations[0].gap_id == "G-1"
    assert remediations[0].action == "redesign"
    assert remediations[1].action == "reimplement"


def test_analyze_gaps_from_verdict():
    from devforge.state.acceptance import AcceptanceVerdict, GoalCheckResult
    verdict = AcceptanceVerdict(
        verdict_id="V-1", project_id="P-1", cycle_id="c-1",
        is_production_ready=False, overall_score=0.5,
        goal_checks=[
            GoalCheckResult(goal="购买流程完整", status="met", reason="ok"),
            GoalCheckResult(goal="退款流程完整", status="unmet", reason="未实现"),
        ],
        gaps=[
            GapItem(gap_id="G-1", description="退款流程缺失", severity="high",
                    attributed_domain="", attributed_capability="",
                    remediation_target="design"),
        ],
    )
    result = analyze_gaps(verdict)
    assert len(result.attributed_gaps) == 1
    assert result.attributed_gaps[0].attributed_domain == "#2"
    assert len(result.remediations) == 1
    assert result.reentry_point == "product_design"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_gap_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement gap analyzer**

```python
# src/devforge/planning/gap_analyzer.py
"""Gap attribution and remediation package generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.state.acceptance import AcceptanceVerdict, GapItem, RemediationPackage


_TARGET_TO_DOMAIN: dict[str, tuple[str, str]] = {
    "design": ("#2", "产品设计"),
    "decomposition": ("#4", "任务分解"),
    "implementation": ("#6", "执行器调度"),
    "testing": ("#10", "集成缝合验证"),
}

_TARGET_TO_ACTION: dict[str, str] = {
    "design": "redesign",
    "decomposition": "reimplement",
    "implementation": "reimplement",
    "testing": "add_test",
}

_TARGET_TO_REENTRY: dict[str, str] = {
    "design": "product_design",
    "decomposition": "task_decomposition",
    "implementation": "batch_dispatch",
    "testing": "batch_verification",
}


@dataclass(slots=True)
class GapAnalysisResult:
    """Result of gap analysis with attribution and remediations."""

    attributed_gaps: list[GapItem] = field(default_factory=list)
    remediations: list[RemediationPackage] = field(default_factory=list)
    reentry_point: str = ""


def attribute_gap_to_domain(gap: GapItem) -> GapItem:
    """Attribute a gap to the correct capability domain based on remediation target."""
    target = gap.remediation_target
    domain, capability = _TARGET_TO_DOMAIN.get(target, ("#6", "执行器调度"))
    return GapItem(
        gap_id=gap.gap_id,
        description=gap.description,
        severity=gap.severity,
        attributed_domain=domain,
        attributed_capability=capability,
        remediation_target=gap.remediation_target,
    )


def generate_remediations(
    gaps: list[GapItem],
    project_id: str = "",
) -> list[RemediationPackage]:
    """Generate remediation work packages for each gap."""
    remediations: list[RemediationPackage] = []
    for gap in gaps:
        action = _TARGET_TO_ACTION.get(gap.remediation_target, "reimplement")
        target_phase = {
            "redesign": "analysis_design",
            "reimplement": "implementation",
            "add_test": "testing",
            "add_feature": "implementation",
            "fix_seam": "implementation",
        }.get(action, "implementation")

        remediations.append(RemediationPackage(
            remediation_id=f"R-{gap.gap_id}",
            gap_id=gap.gap_id,
            action=action,
            target_phase=target_phase,
            description=f"Remediate: {gap.description}",
            affected_work_packages=[],
        ))
    return remediations


def analyze_gaps(verdict: AcceptanceVerdict) -> GapAnalysisResult:
    """Analyze gaps from an acceptance verdict: attribute and generate remediations."""
    attributed: list[GapItem] = []
    for gap in verdict.gaps:
        attributed.append(attribute_gap_to_domain(gap))

    remediations = generate_remediations(attributed, project_id=verdict.project_id)

    # Determine reentry point: highest severity gap's target
    reentry = ""
    if attributed:
        highest = max(attributed, key=lambda g: {"high": 3, "medium": 2, "low": 1}.get(g.severity, 0))
        reentry = _TARGET_TO_REENTRY.get(highest.remediation_target, "batch_dispatch")

    return GapAnalysisResult(
        attributed_gaps=attributed,
        remediations=remediations,
        reentry_point=reentry,
    )
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_gap_analyzer.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/planning/gap_analyzer.py tests/test_gap_analyzer.py
git commit -m "feat: add gap analyzer with domain attribution and remediation generation"
```

---

### Task 5: Wire Acceptance Node into Graph

**Files:**
- Modify: `src/devforge/graph/nodes.py`
- Modify: `src/devforge/graph/runtime_state.py`
- Modify: `src/devforge/planning/__init__.py`
- Test: `tests/test_acceptance_node.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_acceptance_node.py
"""Tests for acceptance_and_gap_check graph node."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import acceptance_and_gap_check_node
from devforge.llm import MockLLMClient


def test_acceptance_node_production_ready():
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "Test", "ring_0_tasks": ["t1"], "user_flows": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "coverage_ratio": 0.9, "closures": []}

    updated = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["feature complete"],
        work_package_results=[{"work_package_id": "WP-1", "status": "completed", "summary": "done"}],
        llm_client=MockLLMClient(),
    )
    assert updated.acceptance_verdict is not None
    assert updated.acceptance_verdict["is_production_ready"] is True
    assert updated.termination_signal is True


def test_acceptance_node_not_ready_triggers_gap_analysis():
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1")
    state.product_design = {"product_name": "Test", "ring_0_tasks": ["t1"], "user_flows": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "closures": []}

    updated = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["feature complete"],
        work_package_results=[{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}],
        llm_client=MockLLMClient(),
    )
    assert updated.acceptance_verdict is not None
    assert updated.acceptance_verdict["is_production_ready"] is False
    assert updated.termination_signal is not True
    assert updated.replan_reason is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance_node.py -v`
Expected: FAIL

- [ ] **Step 3: Add acceptance_verdict field to RuntimeState**

In `src/devforge/graph/runtime_state.py`, add:

```python
    acceptance_verdict: dict[str, object] | None = None
```

- [ ] **Step 4: Implement acceptance_and_gap_check_node**

Append to `src/devforge/graph/nodes.py`:

```python
from devforge.planning.acceptance import evaluate_acceptance
from devforge.planning.gap_analyzer import analyze_gaps


def acceptance_and_gap_check_node(
    state: RuntimeState,
    *,
    acceptance_goals: list[str] | None = None,
    work_package_results: list[dict[str, object]] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Evaluate deliverables against acceptance goals. Set termination or replan."""
    goals = acceptance_goals or []
    results = work_package_results or []
    design = state.product_design or {}
    closure = state.closure_expansion or {}

    verdict = evaluate_acceptance(
        project_id=state.active_project_id or "",
        cycle_id=state.cycle_id or "",
        acceptance_goals=goals,
        work_package_results=results,
        design_summary=design,
        closure_expansion=closure,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )

    state.acceptance_verdict = {
        "verdict_id": verdict.verdict_id,
        "project_id": verdict.project_id,
        "is_production_ready": verdict.is_production_ready,
        "overall_score": verdict.overall_score,
        "summary": verdict.summary,
        "goal_checks": [
            {"goal": gc.goal, "status": gc.status, "reason": gc.reason}
            for gc in verdict.goal_checks
        ],
        "gaps": [
            {"gap_id": g.gap_id, "description": g.description, "severity": g.severity,
             "attributed_domain": g.attributed_domain, "remediation_target": g.remediation_target}
            for g in verdict.gaps
        ],
        "closure_density": {
            "total_ring_0": verdict.closure_density.total_ring_0,
            "covered": verdict.closure_density.covered,
            "coverage_ratio": verdict.closure_density.coverage_ratio,
        } if verdict.closure_density else None,
        "role_evaluations": verdict.role_evaluations,
    }

    if verdict.is_production_ready:
        state.termination_signal = True
    else:
        gap_result = analyze_gaps(verdict)
        state.replan_reason = f"acceptance_gaps:{gap_result.reentry_point}" if gap_result.reentry_point else "acceptance_failed"

    return state
```

- [ ] **Step 5: Update planning __init__.py**

Add exports:
```python
from .acceptance import evaluate_acceptance
from .gap_analyzer import analyze_gaps, attribute_gap_to_domain, generate_remediations, GapAnalysisResult
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance_node.py -v`
Expected: All 2 tests PASS

- [ ] **Step 7: Run full suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/devforge/graph/nodes.py src/devforge/graph/runtime_state.py src/devforge/planning/__init__.py tests/test_acceptance_node.py
git commit -m "feat: wire acceptance_and_gap_check_node into graph with gap analysis"
```

---

### Task 6: Integration Test — Full Acceptance Pipeline

**Files:**
- Create: `tests/test_acceptance_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_acceptance_integration.py
"""Integration: results → seam check → acceptance → gap → remediation."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    product_design_node,
    design_validation_node,
    closure_expansion_node,
    acceptance_and_gap_check_node,
)
from devforge.seams.verifier import verify_seam_compliance
from devforge.planning.gap_analyzer import analyze_gaps
from devforge.state.acceptance import AcceptanceVerdict, GapItem, GoalCheckResult
from devforge.llm import MockLLMClient


def test_full_acceptance_pass_pipeline():
    """All work done → seams verified → acceptance passes → terminate."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1", cycle_id="cycle-005")
    state.product_design = {
        "product_name": "电商平台",
        "ring_0_tasks": ["购买", "支付"],
        "user_flows": [{"role": "buyer"}, {"role": "admin"}],
        "domains": [],
    }
    state.closure_expansion = {"total_ring_0": 2, "total_ring_1": 6, "coverage_ratio": 0.9, "closures": []}

    # Seam verification
    seam = {"seam_id": "S-1", "status": "frozen", "acceptance_criteria": ["API returns JSON"], "artifacts": []}
    seam_result = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "completed", "summary": "API returns JSON correctly"}])
    assert seam_result.compliant is True

    # Acceptance
    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["购买流程完整", "支付安全"],
        work_package_results=[
            {"work_package_id": "WP-1", "status": "completed", "summary": "购买流程实现"},
            {"work_package_id": "WP-2", "status": "completed", "summary": "支付功能完成"},
        ],
        llm_client=llm,
    )
    assert state.acceptance_verdict["is_production_ready"] is True
    assert state.termination_signal is True


def test_full_acceptance_fail_pipeline():
    """Work failed → acceptance fails → gap analysis → replan."""
    llm = MockLLMClient()
    state = RuntimeState(workspace_id="W-1", active_project_id="P-1", cycle_id="cycle-005")
    state.product_design = {"product_name": "电商平台", "ring_0_tasks": ["购买"], "user_flows": [], "domains": []}
    state.closure_expansion = {"total_ring_0": 1, "total_ring_1": 3, "closures": []}

    # Seam broken
    seam = {"seam_id": "S-1", "status": "frozen", "acceptance_criteria": ["API returns JSON"], "artifacts": []}
    seam_result = verify_seam_compliance(seam, [{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}])
    assert seam_result.compliant is False

    # Acceptance
    state = acceptance_and_gap_check_node(
        state,
        acceptance_goals=["购买流程完整"],
        work_package_results=[{"work_package_id": "WP-1", "status": "failed", "summary": "crash"}],
        llm_client=llm,
    )
    assert state.acceptance_verdict["is_production_ready"] is False
    assert state.termination_signal is not True
    assert state.replan_reason is not None
    assert "acceptance" in state.replan_reason
```

- [ ] **Step 2: Run test**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest tests/test_acceptance_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run full suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_acceptance_integration.py
git commit -m "feat: add integration tests for full acceptance pipeline (pass and fail paths)"
```

---

### Task 7: Full Suite Verification

- [ ] **Step 1: Run complete test suite**

Run: `cd /Users/aa/workspace/devforge && uv run python -m pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify new files**

Run: `ls -la src/devforge/state/acceptance.py src/devforge/seams/verifier.py src/devforge/planning/acceptance.py src/devforge/planning/gap_analyzer.py`
Expected: All 4 files exist

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: Plan 3 complete — integration stitching and product acceptance

Implements acceptance plan capabilities #9-#12:
- Acceptance verdict and gap data models
- Seam contract compliance verifier
- LLM-driven acceptance evaluator with role and closure assessment
- Gap analyzer with domain attribution and remediation generation
- acceptance_and_gap_check_node wired into graph
- 7 test files, 22+ test cases"
```
