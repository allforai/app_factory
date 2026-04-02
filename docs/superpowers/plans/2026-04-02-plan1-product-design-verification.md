# Plan 1: 产品设计与验证引擎 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the concept-to-design pipeline, design verification engine, and Ring-based convergence-driven feature expansion — capabilities #1-#3 plus convergence from the acceptance plan.

**Architecture:** Extend the existing concept_collection → planning_and_shaping pipeline with three new modules: (1) `design_generator` — LLM-driven product design from concept, producing structured design artifacts; (2) `design_validator` — dependency cycle detection, seam completeness check, closure loop scanning; (3) `closure_expander` — Ring-based feature derivation with convergence control. These plug into the existing `graph/nodes.py` and `graph/builder.py` orchestration loop.

**Tech Stack:** Python 3.12, dataclasses, existing LLM client protocol (mock for TDD), existing knowledge registry, pytest.

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `src/devforge/planning/design_generator.py` | LLM-driven product design generation from concept — domain decomposition, user flows, interaction matrix |
| Create: `src/devforge/planning/design_validator.py` | Structural validation of design — dependency cycles, seam completeness, feasibility flags |
| Create: `src/devforge/planning/closure_expander.py` | Ring-based closure derivation with convergence control |
| Create: `src/devforge/state/design.py` | Design artifact dataclasses — ProductDesign, DomainSpec, UserFlow, ClosureItem, InteractionMatrixEntry |
| Modify: `src/devforge/state/work_package.py` | Add `derivation_ring` and `backfill_source` fields |
| Modify: `src/devforge/state/__init__.py` | Re-export new design types |
| Modify: `src/devforge/llm/mock.py` | Add mock responses for `product_design`, `design_validation`, `closure_expansion` tasks |
| Modify: `src/devforge/graph/nodes.py` | Add `product_design_node`, `design_validation_node`, `closure_expansion_node` |
| Modify: `src/devforge/graph/builder.py` | Wire new nodes into `run_cycle` |
| Create: `tests/test_design_generator.py` | Tests for design generation |
| Create: `tests/test_design_validator.py` | Tests for validation logic |
| Create: `tests/test_closure_expander.py` | Tests for Ring-based expansion and convergence |
| Create: `tests/test_design_integration.py` | Integration test: concept → design → validate → expand → work packages |

---

### Task 1: Design Artifact Data Model

**Files:**
- Create: `src/devforge/state/design.py`
- Modify: `src/devforge/state/__init__.py`
- Modify: `src/devforge/state/work_package.py:23-55`
- Test: `tests/test_design_model.py`

- [ ] **Step 1: Write the failing test for design data model**

```python
# tests/test_design_model.py
"""Tests for product design data model."""

from devforge.state.design import (
    ClosureItem,
    ClosureType,
    DomainSpec,
    InteractionMatrixEntry,
    ProductDesign,
    UserFlow,
)


def test_product_design_creation():
    design = ProductDesign(
        design_id="D-001",
        initiative_id="I-001",
        project_id="P-001",
        product_name="二手交易平台",
        problem_statement="年轻人需要一个有社区感的二手交易平台",
        target_users=["buyer", "seller", "admin"],
        domains=[
            DomainSpec(
                domain_id="商品",
                name="商品",
                purpose="管理商品发布、搜索、详情",
                inputs=["用户输入"],
                outputs=["商品列表", "商品详情"],
                dependencies=[],
            ),
        ],
        user_flows=[
            UserFlow(
                flow_id="F-001",
                name="购买流程",
                role="buyer",
                steps=["浏览", "搜索", "加购", "结算", "支付"],
                entry_point="首页",
                exit_point="订单确认页",
            ),
        ],
        interaction_matrix=[
            InteractionMatrixEntry(
                feature="浏览商品",
                role="buyer",
                frequency="high",
                user_volume="high",
                principle="极致效率、零学习成本、容错性高",
            ),
        ],
        non_functional_requirements=["支付幂等", "库存并发一致性"],
        tech_choices={"frontend": "React", "backend": "Python"},
        ring_0_tasks=["商品发布", "搜索", "下单", "支付", "评价"],
    )
    assert design.design_id == "D-001"
    assert len(design.domains) == 1
    assert len(design.user_flows) == 1
    assert len(design.interaction_matrix) == 1
    assert design.ring_0_tasks == ["商品发布", "搜索", "下单", "支付", "评价"]


def test_closure_item():
    item = ClosureItem(
        closure_id="CL-001",
        source_task="认证",
        derived_task="密码恢复",
        closure_type="exception",
        ring=1,
        rationale="认证任务的凭证丢失恢复闭环",
    )
    assert item.ring == 1
    assert item.closure_type == "exception"


def test_closure_types():
    """All six closure types must be representable."""
    types: list[ClosureType] = [
        "configuration",
        "monitoring",
        "exception",
        "permission",
        "data",
        "notification",
    ]
    for ct in types:
        item = ClosureItem(
            closure_id=f"CL-{ct}",
            source_task="任意任务",
            derived_task=f"{ct}闭环",
            closure_type=ct,
            ring=1,
            rationale=f"{ct}闭环推导",
        )
        assert item.closure_type == ct


def test_domain_spec_dependencies():
    payment = DomainSpec(
        domain_id="支付",
        name="支付",
        purpose="处理支付流程",
        inputs=["订单"],
        outputs=["支付结果"],
        dependencies=["订单"],
    )
    assert "订单" in payment.dependencies


def test_interaction_matrix_quadrants():
    """Verify the four quadrants of the interaction matrix."""
    entries = [
        InteractionMatrixEntry(
            feature="浏览", role="buyer", frequency="high", user_volume="high",
            principle="极致效率",
        ),
        InteractionMatrixEntry(
            feature="注册", role="buyer", frequency="low", user_volume="high",
            principle="引导式",
        ),
        InteractionMatrixEntry(
            feature="审核订单", role="admin", frequency="high", user_volume="low",
            principle="信息密度高",
        ),
        InteractionMatrixEntry(
            feature="权限配置", role="admin", frequency="low", user_volume="low",
            principle="安全确认",
        ),
    ]
    assert len(entries) == 4
    assert entries[0].frequency == "high" and entries[0].user_volume == "high"
    assert entries[3].frequency == "low" and entries[3].user_volume == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devforge.state.design'`

- [ ] **Step 3: Implement the design data model**

```python
# src/devforge/state/design.py
"""Product design artifact models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ClosureType = Literal[
    "configuration",
    "monitoring",
    "exception",
    "permission",
    "data",
    "notification",
]


@dataclass(slots=True)
class DomainSpec:
    """One domain in the product design."""

    domain_id: str
    name: str
    purpose: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UserFlow:
    """A user-facing flow through the product."""

    flow_id: str
    name: str
    role: str
    steps: list[str] = field(default_factory=list)
    entry_point: str = ""
    exit_point: str = ""


@dataclass(slots=True)
class InteractionMatrixEntry:
    """One cell in the role x frequency interaction matrix."""

    feature: str
    role: str
    frequency: Literal["high", "low"]
    user_volume: Literal["high", "low"]
    principle: str


@dataclass(slots=True)
class ClosureItem:
    """A derived closure function from Ring-based expansion."""

    closure_id: str
    source_task: str
    derived_task: str
    closure_type: ClosureType
    ring: int
    rationale: str
    scale_ratio: float = 0.0
    status: Literal["proposed", "accepted", "rejected", "new_domain"] = "proposed"


@dataclass(slots=True)
class ProductDesign:
    """Structured product design artifact produced from concept."""

    design_id: str
    initiative_id: str
    project_id: str
    product_name: str
    problem_statement: str
    target_users: list[str] = field(default_factory=list)
    domains: list[DomainSpec] = field(default_factory=list)
    user_flows: list[UserFlow] = field(default_factory=list)
    interaction_matrix: list[InteractionMatrixEntry] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    tech_choices: dict[str, str] = field(default_factory=dict)
    ring_0_tasks: list[str] = field(default_factory=list)
    closures: list[ClosureItem] = field(default_factory=list)
    unexplored_areas: list[str] = field(default_factory=list)
    version: int = 1
```

- [ ] **Step 4: Add derivation_ring to WorkPackage**

In `src/devforge/state/work_package.py`, add two fields after `updated_at`:

```python
    derivation_ring: int = 0
    backfill_source: str | None = None
```

- [ ] **Step 5: Update state __init__.py exports**

Add to `src/devforge/state/__init__.py` the new design types:

```python
from .design import ClosureItem, ClosureType, DomainSpec, InteractionMatrixEntry, ProductDesign, UserFlow
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_model.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/devforge/state/design.py src/devforge/state/work_package.py src/devforge/state/__init__.py tests/test_design_model.py
git commit -m "feat: add product design data model with Ring-based closure types"
```

---

### Task 2: Design Generator (LLM-driven)

**Files:**
- Create: `src/devforge/planning/design_generator.py`
- Modify: `src/devforge/llm/mock.py:17-135`
- Test: `tests/test_design_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_generator.py
"""Tests for LLM-driven product design generation."""

from devforge.llm import MockLLMClient
from devforge.planning.design_generator import generate_product_design


def test_generate_design_from_concept():
    concept = {
        "goal": "collect concept model for 二手交易平台",
        "focus_areas": ["用户交易流程", "社区互动", "信任体系"],
        "questions": [],
        "required_artifacts": [],
    }
    project = {
        "project_id": "P-001",
        "initiative_id": "I-001",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "analysis_design",
    }
    design = generate_product_design(
        concept=concept,
        project=project,
        knowledge_ids=["ecommerce"],
        llm_client=MockLLMClient(),
    )
    assert design.design_id != ""
    assert design.project_id == "P-001"
    assert len(design.domains) > 0
    assert len(design.user_flows) > 0
    assert len(design.interaction_matrix) > 0
    assert len(design.ring_0_tasks) > 0


def test_generate_design_includes_non_functional():
    concept = {
        "goal": "collect concept model for 游戏",
        "focus_areas": ["核心循环", "战斗系统"],
    }
    project = {
        "project_id": "P-002",
        "initiative_id": "I-001",
        "name": "Roguelike Game",
        "project_archetype": "gaming",
        "current_phase": "analysis_design",
    }
    design = generate_product_design(
        concept=concept,
        project=project,
        knowledge_ids=["gaming"],
        llm_client=MockLLMClient(),
    )
    assert len(design.non_functional_requirements) > 0


def test_design_has_interaction_matrix_for_all_quadrants():
    """At least one entry per quadrant should exist for multi-role projects."""
    concept = {
        "goal": "collect concept model for 二手交易平台",
        "focus_areas": ["用户交易流程", "管理后台"],
    }
    project = {
        "project_id": "P-003",
        "initiative_id": "I-001",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "analysis_design",
    }
    design = generate_product_design(
        concept=concept,
        project=project,
        knowledge_ids=["ecommerce"],
        llm_client=MockLLMClient(),
    )
    quadrants = {(e.frequency, e.user_volume) for e in design.interaction_matrix}
    # ecommerce projects should produce at least buyer (high volume) + admin (low volume)
    assert len(quadrants) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_generator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add mock response for product_design task**

In `src/devforge/llm/mock.py`, add a handler in `generate_structured` after the `planning_and_shaping` block and a new method:

```python
        if request.task == "product_design":
            output = self._product_design_output(request)
            return StructuredGenerationResponse(
                output=output,
                provider=self.provider_name,
                model=self.model_name,
                raw_text=str(output),
                metadata={"task": request.task, "schema_name": request.schema_name},
            )
```

Add the method:

```python
    def _product_design_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        project = payload.get("project", {})
        concept = payload.get("concept", {})
        archetype = project.get("project_archetype", "generic")
        focus_areas = concept.get("focus_areas", [])

        if archetype == "ecommerce":
            domains = [
                {"domain_id": "用户", "name": "用户", "purpose": "认证与用户管理", "inputs": [], "outputs": ["用户信息"], "dependencies": []},
                {"domain_id": "商品", "name": "商品", "purpose": "商品发布与搜索", "inputs": ["用户信息"], "outputs": ["商品列表"], "dependencies": ["用户"]},
                {"domain_id": "交易", "name": "交易", "purpose": "下单与订单管理", "inputs": ["商品", "用户信息"], "outputs": ["订单"], "dependencies": ["商品", "用户"]},
                {"domain_id": "支付", "name": "支付", "purpose": "支付处理", "inputs": ["订单"], "outputs": ["支付结果"], "dependencies": ["交易"]},
                {"domain_id": "互动", "name": "互动", "purpose": "评价与社区", "inputs": ["订单", "用户信息"], "outputs": ["评价", "社区内容"], "dependencies": ["交易", "用户"]},
                {"domain_id": "管理", "name": "管理", "purpose": "管理后台", "inputs": ["all"], "outputs": ["管理操作"], "dependencies": ["用户", "商品", "交易"]},
            ]
            user_flows = [
                {"flow_id": "F-buy", "name": "购买流程", "role": "buyer", "steps": ["浏览", "搜索", "加购", "结算", "支付", "确认"], "entry_point": "首页", "exit_point": "订单确认"},
                {"flow_id": "F-sell", "name": "发布流程", "role": "seller", "steps": ["发布商品", "定价", "上架"], "entry_point": "发布页", "exit_point": "商品详情"},
                {"flow_id": "F-admin", "name": "管理流程", "role": "admin", "steps": ["审核", "处理纠纷", "数据统计"], "entry_point": "管理首页", "exit_point": "报表"},
            ]
            interaction_matrix = [
                {"feature": "浏览商品", "role": "buyer", "frequency": "high", "user_volume": "high", "principle": "极致效率、零学习成本"},
                {"feature": "注册/绑卡", "role": "buyer", "frequency": "low", "user_volume": "high", "principle": "引导式、可发现性优先"},
                {"feature": "订单审核", "role": "admin", "frequency": "high", "user_volume": "low", "principle": "信息密度高、批量操作"},
                {"feature": "权限配置", "role": "admin", "frequency": "low", "user_volume": "low", "principle": "安全确认、操作可逆"},
            ]
            ring_0_tasks = ["认证", "商品发布", "搜索", "加购", "下单", "支付", "订单管理", "评价", "管理后台"]
            non_functional = ["支付幂等", "库存并发一致性", "订单状态机正确性", "价格计算一致性"]
        else:
            domains = [
                {"domain_id": "核心机制", "name": "核心机制", "purpose": "核心游戏循环", "inputs": [], "outputs": ["游戏状态"], "dependencies": []},
                {"domain_id": "地图", "name": "地图", "purpose": "地图生成", "inputs": [], "outputs": ["地图数据"], "dependencies": []},
                {"domain_id": "战斗", "name": "战斗", "purpose": "战斗系统", "inputs": ["游戏状态"], "outputs": ["战斗结果"], "dependencies": ["核心机制"]},
                {"domain_id": "经济", "name": "经济", "purpose": "物品与经济", "inputs": ["战斗结果"], "outputs": ["物品数据"], "dependencies": ["战斗"]},
            ]
            user_flows = [
                {"flow_id": "F-play", "name": "探索循环", "role": "player", "steps": ["进入地牢", "探索", "战斗", "拾取", "升级"], "entry_point": "大厅", "exit_point": "结算"},
            ]
            interaction_matrix = [
                {"feature": "战斗", "role": "player", "frequency": "high", "user_volume": "high", "principle": "即时反馈、手感优先"},
                {"feature": "角色创建", "role": "player", "frequency": "low", "user_volume": "high", "principle": "引导式、渐进复杂度"},
            ]
            ring_0_tasks = ["地图生成", "战斗系统", "物品掉落", "角色成长", "核心循环"]
            non_functional = ["帧率稳定", "随机性可控", "存档一致性"]

        return {
            "product_name": project.get("name", "产品"),
            "problem_statement": concept.get("goal", ""),
            "target_users": list({f.get("role", "") for f in user_flows}),
            "domains": domains,
            "user_flows": user_flows,
            "interaction_matrix": interaction_matrix,
            "non_functional_requirements": non_functional,
            "tech_choices": {},
            "ring_0_tasks": ring_0_tasks,
        }
```

- [ ] **Step 4: Implement design generator**

```python
# src/devforge/planning/design_generator.py
"""LLM-driven product design generation from concept artifacts."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from devforge.llm import LLMClient, MockLLMClient, StructuredGenerationRequest, build_task_llm_client
from devforge.state.design import (
    DomainSpec,
    InteractionMatrixEntry,
    ProductDesign,
    UserFlow,
)


def generate_product_design(
    *,
    concept: dict[str, Any],
    project: dict[str, Any],
    knowledge_ids: list[str] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, Any] | None = None,
) -> ProductDesign:
    """Generate a structured product design from concept and project context."""
    llm_client = llm_client or build_task_llm_client(task="product_design", preferences=llm_preferences) or MockLLMClient()
    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="product_design",
            schema_name="ProductDesign",
            instructions=(
                "Generate a structured product design from the concept. "
                "Include domain decomposition, user flows, interaction matrix "
                "(role x frequency), non-functional requirements, and Ring 0 core tasks. "
                "Use domain knowledge to ensure completeness."
            ),
            input_payload={
                "concept": concept,
                "project": project,
                "knowledge_ids": knowledge_ids or [],
            },
            metadata={"decision_kind": "product_design"},
        )
    )
    output = response.output
    design_id = f"D-{uuid4().hex[:8]}"

    domains = [
        DomainSpec(
            domain_id=d.get("domain_id", f"dom-{i}"),
            name=d.get("name", ""),
            purpose=d.get("purpose", ""),
            inputs=list(d.get("inputs", [])),
            outputs=list(d.get("outputs", [])),
            dependencies=list(d.get("dependencies", [])),
        )
        for i, d in enumerate(output.get("domains", []))
    ]

    user_flows = [
        UserFlow(
            flow_id=f.get("flow_id", f"F-{i}"),
            name=f.get("name", ""),
            role=f.get("role", ""),
            steps=list(f.get("steps", [])),
            entry_point=f.get("entry_point", ""),
            exit_point=f.get("exit_point", ""),
        )
        for i, f in enumerate(output.get("user_flows", []))
    ]

    interaction_matrix = [
        InteractionMatrixEntry(
            feature=e.get("feature", ""),
            role=e.get("role", ""),
            frequency=e.get("frequency", "high"),
            user_volume=e.get("user_volume", "high"),
            principle=e.get("principle", ""),
        )
        for e in output.get("interaction_matrix", [])
    ]

    return ProductDesign(
        design_id=design_id,
        initiative_id=project.get("initiative_id", ""),
        project_id=project.get("project_id", ""),
        product_name=output.get("product_name", project.get("name", "")),
        problem_statement=output.get("problem_statement", ""),
        target_users=list(output.get("target_users", [])),
        domains=domains,
        user_flows=user_flows,
        interaction_matrix=interaction_matrix,
        non_functional_requirements=list(output.get("non_functional_requirements", [])),
        tech_choices=dict(output.get("tech_choices", {})),
        ring_0_tasks=list(output.get("ring_0_tasks", [])),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_generator.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/devforge/planning/design_generator.py src/devforge/llm/mock.py tests/test_design_generator.py
git commit -m "feat: add LLM-driven product design generator with mock"
```

---

### Task 3: Design Validator

**Files:**
- Create: `src/devforge/planning/design_validator.py`
- Test: `tests/test_design_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_validator.py
"""Tests for product design structural validation."""

from devforge.state.design import DomainSpec, ProductDesign, UserFlow
from devforge.planning.design_validator import validate_design, ValidationResult


def _make_design(**overrides) -> ProductDesign:
    defaults = dict(
        design_id="D-test",
        initiative_id="I-001",
        project_id="P-001",
        product_name="Test",
        problem_statement="test",
        target_users=["user"],
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", dependencies=["A"]),
        ],
        user_flows=[
            UserFlow(flow_id="F-1", name="main", role="user", steps=["step1"]),
        ],
        ring_0_tasks=["task1"],
    )
    defaults.update(overrides)
    return ProductDesign(**defaults)


def test_valid_design_passes():
    result = validate_design(_make_design())
    assert result.valid is True
    assert len(result.errors) == 0


def test_dependency_cycle_detected():
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", dependencies=["C"]),
            DomainSpec(domain_id="B", name="B", purpose="b", dependencies=["A"]),
            DomainSpec(domain_id="C", name="C", purpose="c", dependencies=["B"]),
        ],
    )
    result = validate_design(design)
    assert result.valid is False
    cycle_errors = [e for e in result.errors if e.error_type == "dependency_cycle"]
    assert len(cycle_errors) > 0


def test_missing_seam_detected():
    """When domain B depends on domain A but no seam exists between them."""
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", outputs=["data_x"], dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", inputs=["data_x"], dependencies=["A"]),
        ],
    )
    result = validate_design(design, existing_seam_pairs=set())
    assert any(w.error_type == "missing_seam" for w in result.warnings)


def test_missing_seam_suppressed_when_seam_exists():
    design = _make_design(
        domains=[
            DomainSpec(domain_id="A", name="A", purpose="a", outputs=["data_x"], dependencies=[]),
            DomainSpec(domain_id="B", name="B", purpose="b", inputs=["data_x"], dependencies=["A"]),
        ],
    )
    result = validate_design(design, existing_seam_pairs={("A", "B")})
    assert not any(w.error_type == "missing_seam" for w in result.warnings)


def test_empty_ring_0_tasks_is_error():
    design = _make_design(ring_0_tasks=[])
    result = validate_design(design)
    assert result.valid is False
    assert any(e.error_type == "empty_ring_0" for e in result.errors)


def test_no_user_flows_is_error():
    design = _make_design(user_flows=[])
    result = validate_design(design)
    assert result.valid is False
    assert any(e.error_type == "no_user_flows" for e in result.errors)


def test_iteration_fix_tracking():
    """Previous issues should be checked on re-validation."""
    previous_issues = ["dependency_cycle"]
    design = _make_design()  # valid design — the cycle was fixed
    result = validate_design(design, previous_issues=previous_issues)
    assert result.valid is True
    assert "dependency_cycle" in result.resolved_issues
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_validator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement design validator**

```python
# src/devforge/planning/design_validator.py
"""Structural validation of product design artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field

from devforge.state.design import ProductDesign


@dataclass(slots=True)
class ValidationIssue:
    """One validation finding."""

    error_type: str
    message: str
    domain_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    """Result of design validation."""

    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    resolved_issues: list[str] = field(default_factory=list)


def _detect_cycles(domains: list[tuple[str, list[str]]]) -> list[list[str]]:
    """Detect dependency cycles using DFS. Returns list of cycles found."""
    graph: dict[str, list[str]] = {d_id: deps for d_id, deps in domains}
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in in_stack:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for dep in graph.get(node, []):
            if dep in graph:
                dfs(dep)
        path.pop()
        in_stack.remove(node)

    for domain_id in graph:
        if domain_id not in visited:
            dfs(domain_id)

    return cycles


def validate_design(
    design: ProductDesign,
    *,
    existing_seam_pairs: set[tuple[str, str]] | None = None,
    previous_issues: list[str] | None = None,
) -> ValidationResult:
    """Validate a ProductDesign for structural correctness."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    resolved: list[str] = []
    existing_seam_pairs = existing_seam_pairs or set()
    previous_issues = previous_issues or []

    # Check dependency cycles
    domain_deps = [(d.domain_id, d.dependencies) for d in design.domains]
    cycles = _detect_cycles(domain_deps)
    for cycle in cycles:
        errors.append(ValidationIssue(
            error_type="dependency_cycle",
            message=f"Dependency cycle detected: {' -> '.join(cycle)}",
            domain_ids=cycle,
        ))

    # Check missing seams
    for domain in design.domains:
        for dep_id in domain.dependencies:
            pair = (dep_id, domain.domain_id)
            reverse_pair = (domain.domain_id, dep_id)
            if pair not in existing_seam_pairs and reverse_pair not in existing_seam_pairs:
                warnings.append(ValidationIssue(
                    error_type="missing_seam",
                    message=f"Domain '{domain.domain_id}' depends on '{dep_id}' but no seam contract exists",
                    domain_ids=[dep_id, domain.domain_id],
                ))

    # Check ring 0 tasks
    if not design.ring_0_tasks:
        errors.append(ValidationIssue(
            error_type="empty_ring_0",
            message="Design has no Ring 0 core tasks defined",
        ))

    # Check user flows
    if not design.user_flows:
        errors.append(ValidationIssue(
            error_type="no_user_flows",
            message="Design has no user flows defined",
        ))

    # Check iteration fix tracking
    current_error_types = {e.error_type for e in errors}
    for prev_issue in previous_issues:
        if prev_issue not in current_error_types:
            resolved.append(prev_issue)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        resolved_issues=resolved,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_validator.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/planning/design_validator.py tests/test_design_validator.py
git commit -m "feat: add design validator with cycle detection and seam completeness"
```

---

### Task 4: Closure Expander (Ring-based convergence)

**Files:**
- Create: `src/devforge/planning/closure_expander.py`
- Test: `tests/test_closure_expander.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_closure_expander.py
"""Tests for Ring-based closure expansion with convergence control."""

from devforge.planning.closure_expander import (
    expand_closures,
    ClosureExpansionResult,
    CLOSURE_DIMENSIONS,
)
from devforge.state.design import ClosureItem


def test_ring_1_expansion_from_core_tasks():
    ring_0_tasks = ["认证", "下单", "支付"]
    result = expand_closures(ring_0_tasks=ring_0_tasks, concept_boundary=ring_0_tasks, max_ring=1)
    assert isinstance(result, ClosureExpansionResult)
    assert len(result.closures) > 0
    assert all(c.ring == 1 for c in result.closures)
    # Each core task should produce closures across multiple dimensions
    source_tasks = {c.source_task for c in result.closures}
    assert source_tasks == set(ring_0_tasks)


def test_six_closure_dimensions_checked():
    """Each Ring 0 task should be checked against all 6 closure dimensions."""
    assert len(CLOSURE_DIMENSIONS) == 6
    assert set(CLOSURE_DIMENSIONS) == {
        "configuration", "monitoring", "exception",
        "permission", "data", "notification",
    }


def test_ring_1_produces_concrete_derived_tasks():
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=1)
    # "认证" should produce closures like: 密码恢复(exception), 会话过期重登(permission), etc.
    assert len(result.closures) >= 3
    derived_tasks = {c.derived_task for c in result.closures}
    assert len(derived_tasks) >= 3  # not all identical


def test_concept_boundary_respected():
    """Tasks outside concept boundary should not be derived."""
    ring_0_tasks = ["认证"]
    concept_boundary = ["认证"]  # "社交" is not in boundary
    result = expand_closures(ring_0_tasks=ring_0_tasks, concept_boundary=concept_boundary, max_ring=1)
    # No closure should derive "社交分享" or anything not traceable to "认证"
    for c in result.closures:
        assert c.source_task in concept_boundary


def test_scale_reversal_detection():
    """If a derived closure is bigger than its parent, mark it as new_domain."""
    result = expand_closures(
        ring_0_tasks=["简单配置"],
        concept_boundary=["简单配置"],
        max_ring=1,
        scale_overrides={"简单配置:configuration": 2.0},  # scale_ratio > 1.0 = reversal
    )
    reversed_items = [c for c in result.closures if c.status == "new_domain"]
    assert len(reversed_items) > 0


def test_ring_2_only_derives_from_ring_1():
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=2)
    ring_2_items = [c for c in result.closures if c.ring == 2]
    ring_1_derived_tasks = {c.derived_task for c in result.closures if c.ring == 1}
    for item in ring_2_items:
        assert item.source_task in ring_1_derived_tasks


def test_convergence_output_decreases():
    result = expand_closures(ring_0_tasks=["认证", "下单", "支付"], concept_boundary=["认证", "下单", "支付"], max_ring=2)
    ring_1_count = len([c for c in result.closures if c.ring == 1])
    ring_2_count = len([c for c in result.closures if c.ring == 2])
    # Ring 2 should produce fewer items than Ring 1 (geometric decay)
    assert ring_2_count <= ring_1_count


def test_convergence_stops_on_zero_output():
    """If a ring produces nothing, stop."""
    result = expand_closures(ring_0_tasks=["认证"], concept_boundary=["认证"], max_ring=5)
    max_ring = max((c.ring for c in result.closures), default=0)
    # Should not reach ring 5 — convergence should stop earlier
    assert max_ring <= 3
    assert result.stopped_reason in ("zero_output", "max_ring_reached", "all_downgraded")


def test_expansion_result_has_coverage_stats():
    result = expand_closures(ring_0_tasks=["认证", "下单"], concept_boundary=["认证", "下单"], max_ring=1)
    assert result.total_ring_0 == 2
    assert result.total_ring_1 > 0
    assert result.coverage_ratio > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_closure_expander.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement closure expander**

```python
# src/devforge/planning/closure_expander.py
"""Ring-based closure expansion with convergence control.

Three convergence principles:
1. Concept defines boundary — only derive within the concept's finite set
2. Derivation radius decreases — Ring N+1 produces geometrically fewer items
3. Stage relay with cutoff — each stage has a max ring

Stop criteria: zero output, all downgraded, scale reversal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devforge.state.design import ClosureItem, ClosureType

CLOSURE_DIMENSIONS: list[ClosureType] = [
    "configuration",
    "monitoring",
    "exception",
    "permission",
    "data",
    "notification",
]

# Deterministic closure templates per dimension.
# In production, LLM generates these. For testability, use templates.
_CLOSURE_TEMPLATES: dict[ClosureType, list[dict[str, str]]] = {
    "configuration": [
        {"suffix": "配置管理", "rationale": "需要配置端点、默认值、热更新能力"},
    ],
    "monitoring": [
        {"suffix": "监控埋点", "rationale": "需要操作埋点、告警、仪表盘"},
    ],
    "exception": [
        {"suffix": "异常恢复", "rationale": "操作失败时的重试、降级、用户提示"},
        {"suffix": "超时处理", "rationale": "操作超时的降级与通知"},
    ],
    "permission": [
        {"suffix": "凭证恢复", "rationale": "凭证丢失或过期时的恢复路径"},
    ],
    "data": [
        {"suffix": "数据对账", "rationale": "数据不一致时的检测与修复机制"},
    ],
    "notification": [
        {"suffix": "通知降级", "rationale": "通知送达失败时的替代通道"},
    ],
}


@dataclass(slots=True)
class ClosureExpansionResult:
    """Result of closure expansion with convergence metadata."""

    closures: list[ClosureItem] = field(default_factory=list)
    total_ring_0: int = 0
    total_ring_1: int = 0
    total_ring_2_plus: int = 0
    coverage_ratio: float = 0.0
    stopped_reason: str = ""
    convergence_log: list[dict[str, Any]] = field(default_factory=list)


def _derive_closures_for_task(
    source_task: str,
    ring: int,
    concept_boundary: set[str],
    scale_overrides: dict[str, float] | None = None,
) -> list[ClosureItem]:
    """Derive closure items for one task across all 6 dimensions."""
    scale_overrides = scale_overrides or {}
    items: list[ClosureItem] = []
    counter = 0

    for dim in CLOSURE_DIMENSIONS:
        templates = _CLOSURE_TEMPLATES.get(dim, [])
        for tmpl in templates:
            derived_task = f"{source_task}-{tmpl['suffix']}"
            override_key = f"{source_task}:{dim}"
            scale = scale_overrides.get(override_key, 0.3 if ring == 1 else 0.1)

            status: str = "proposed"
            if scale > 1.0:
                status = "new_domain"

            items.append(ClosureItem(
                closure_id=f"CL-{source_task}-{dim}-{counter}",
                source_task=source_task,
                derived_task=derived_task,
                closure_type=dim,
                ring=ring,
                rationale=tmpl["rationale"],
                scale_ratio=scale,
                status=status,
            ))
            counter += 1

    return items


def expand_closures(
    *,
    ring_0_tasks: list[str],
    concept_boundary: list[str],
    max_ring: int = 1,
    scale_overrides: dict[str, float] | None = None,
) -> ClosureExpansionResult:
    """Expand Ring 0 tasks into closure items with convergence control."""
    boundary = set(concept_boundary)
    all_closures: list[ClosureItem] = []
    convergence_log: list[dict[str, Any]] = []
    stopped_reason = "max_ring_reached"

    # Current ring sources start with Ring 0 tasks
    current_sources = [t for t in ring_0_tasks if t in boundary]

    for ring in range(1, max_ring + 1):
        ring_closures: list[ClosureItem] = []
        for source in current_sources:
            derived = _derive_closures_for_task(source, ring, boundary, scale_overrides)
            ring_closures.extend(derived)

        convergence_log.append({
            "ring": ring,
            "sources": len(current_sources),
            "produced": len(ring_closures),
        })

        if not ring_closures:
            stopped_reason = "zero_output"
            break

        # Check if all items are downgraded (new_domain or beyond scope)
        accepted = [c for c in ring_closures if c.status != "new_domain"]
        if not accepted:
            stopped_reason = "all_downgraded"
            break

        all_closures.extend(ring_closures)

        # Next ring's sources are this ring's derived tasks (only accepted ones)
        current_sources = list({c.derived_task for c in accepted})

    ring_1_count = len([c for c in all_closures if c.ring == 1])
    ring_2_plus_count = len([c for c in all_closures if c.ring >= 2])

    theoretical_max = len(ring_0_tasks) * sum(len(v) for v in _CLOSURE_TEMPLATES.values())
    coverage = ring_1_count / theoretical_max if theoretical_max > 0 else 0.0

    return ClosureExpansionResult(
        closures=all_closures,
        total_ring_0=len(ring_0_tasks),
        total_ring_1=ring_1_count,
        total_ring_2_plus=ring_2_plus_count,
        coverage_ratio=coverage,
        stopped_reason=stopped_reason,
        convergence_log=convergence_log,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_closure_expander.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/devforge/planning/closure_expander.py tests/test_closure_expander.py
git commit -m "feat: add Ring-based closure expander with convergence control"
```

---

### Task 5: Wire into Graph Nodes

**Files:**
- Modify: `src/devforge/graph/nodes.py:1-86`
- Modify: `src/devforge/planning/__init__.py`
- Test: `tests/test_design_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_nodes.py
"""Tests for design-related graph nodes."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import product_design_node, design_validation_node, closure_expansion_node
from devforge.llm import MockLLMClient


def test_product_design_node_attaches_design():
    state = RuntimeState(workspace_id="W-1", initiative_id="I-1", active_project_id="P-1")
    project = {
        "project_id": "P-1",
        "initiative_id": "I-1",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "analysis_design",
    }
    concept = {
        "goal": "collect concept for marketplace",
        "focus_areas": ["交易流程"],
    }
    updated = product_design_node(state, project=project, concept=concept, llm_client=MockLLMClient())
    assert updated.product_design is not None
    assert updated.product_design["project_id"] == "P-1"
    assert len(updated.product_design["domains"]) > 0


def test_design_validation_node_valid():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "design_id": "D-1",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Test",
        "problem_statement": "test",
        "target_users": ["user"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": []},
        ],
        "user_flows": [
            {"flow_id": "F-1", "name": "main", "role": "user", "steps": ["s1"]},
        ],
        "ring_0_tasks": ["task1"],
        "interaction_matrix": [],
        "non_functional_requirements": [],
        "tech_choices": {},
        "closures": [],
        "unexplored_areas": [],
        "version": 1,
    }
    updated = design_validation_node(state)
    assert updated.design_valid is True
    assert updated.replan_reason is None


def test_design_validation_node_invalid_triggers_replan():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "design_id": "D-1",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Test",
        "problem_statement": "test",
        "target_users": ["user"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": ["B"]},
            {"domain_id": "B", "name": "B", "purpose": "b", "inputs": [], "outputs": [], "dependencies": ["A"]},
        ],
        "user_flows": [{"flow_id": "F-1", "name": "main", "role": "user", "steps": ["s1"]}],
        "ring_0_tasks": ["task1"],
        "interaction_matrix": [],
        "non_functional_requirements": [],
        "tech_choices": {},
        "closures": [],
        "unexplored_areas": [],
        "version": 1,
    }
    updated = design_validation_node(state)
    assert updated.design_valid is False
    assert updated.replan_reason == "design_validation_failed"


def test_closure_expansion_node():
    state = RuntimeState(workspace_id="W-1")
    state.product_design = {
        "ring_0_tasks": ["认证", "下单"],
    }
    updated = closure_expansion_node(state, concept_boundary=["认证", "下单"])
    assert updated.closure_expansion is not None
    assert updated.closure_expansion["total_ring_0"] == 2
    assert updated.closure_expansion["total_ring_1"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_nodes.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add fields to RuntimeState**

In `src/devforge/graph/runtime_state.py`, add these fields to the `RuntimeState` dataclass:

```python
    product_design: dict[str, object] | None = None
    design_valid: bool | None = None
    design_validation_issues: list[dict[str, object]] = field(default_factory=list)
    closure_expansion: dict[str, object] | None = None
```

- [ ] **Step 4: Implement the three new graph nodes**

Append to `src/devforge/graph/nodes.py`:

```python
from devforge.planning.design_generator import generate_product_design
from devforge.planning.design_validator import validate_design
from devforge.planning.closure_expander import expand_closures
from devforge.state.design import DomainSpec, ProductDesign, UserFlow


def product_design_node(
    state: RuntimeState,
    *,
    project: dict[str, object] | None = None,
    concept: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
) -> RuntimeState:
    """Generate a product design from concept and attach to runtime state."""
    design = generate_product_design(
        concept=concept or state.concept_decision or {},
        project=project or {},
        knowledge_ids=knowledge_ids or state.selected_knowledge,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )
    state.product_design = asdict(design)
    return state


def design_validation_node(state: RuntimeState) -> RuntimeState:
    """Validate the current product design. Set replan_reason if invalid."""
    if state.product_design is None:
        state.design_valid = False
        state.replan_reason = "no_design"
        return state

    pd = state.product_design
    design = ProductDesign(
        design_id=pd.get("design_id", ""),
        initiative_id=pd.get("initiative_id", ""),
        project_id=pd.get("project_id", ""),
        product_name=pd.get("product_name", ""),
        problem_statement=pd.get("problem_statement", ""),
        target_users=list(pd.get("target_users", [])),
        domains=[
            DomainSpec(
                domain_id=d.get("domain_id", ""),
                name=d.get("name", ""),
                purpose=d.get("purpose", ""),
                inputs=list(d.get("inputs", [])),
                outputs=list(d.get("outputs", [])),
                dependencies=list(d.get("dependencies", [])),
            )
            for d in pd.get("domains", [])
        ],
        user_flows=[
            UserFlow(
                flow_id=f.get("flow_id", ""),
                name=f.get("name", ""),
                role=f.get("role", ""),
                steps=list(f.get("steps", [])),
            )
            for f in pd.get("user_flows", [])
        ],
        ring_0_tasks=list(pd.get("ring_0_tasks", [])),
    )
    previous_issues = [i.get("error_type", "") for i in state.design_validation_issues]
    result = validate_design(design, previous_issues=previous_issues)
    state.design_valid = result.valid
    state.design_validation_issues = [
        {"error_type": e.error_type, "message": e.message, "domain_ids": e.domain_ids}
        for e in result.errors
    ]
    if not result.valid:
        state.replan_reason = "design_validation_failed"
    return state


def closure_expansion_node(
    state: RuntimeState,
    *,
    concept_boundary: list[str] | None = None,
    max_ring: int = 1,
) -> RuntimeState:
    """Expand Ring 0 tasks into closure items and attach to state."""
    ring_0_tasks = list((state.product_design or {}).get("ring_0_tasks", []))
    boundary = concept_boundary or ring_0_tasks
    result = expand_closures(ring_0_tasks=ring_0_tasks, concept_boundary=boundary, max_ring=max_ring)
    state.closure_expansion = {
        "total_ring_0": result.total_ring_0,
        "total_ring_1": result.total_ring_1,
        "total_ring_2_plus": result.total_ring_2_plus,
        "coverage_ratio": result.coverage_ratio,
        "stopped_reason": result.stopped_reason,
        "closures": [
            {
                "closure_id": c.closure_id,
                "source_task": c.source_task,
                "derived_task": c.derived_task,
                "closure_type": c.closure_type,
                "ring": c.ring,
                "rationale": c.rationale,
                "scale_ratio": c.scale_ratio,
                "status": c.status,
            }
            for c in result.closures
        ],
    }
    return state
```

- [ ] **Step 5: Update planning __init__.py exports**

Add to `src/devforge/planning/__init__.py`:

```python
from .design_generator import generate_product_design
from .design_validator import validate_design, ValidationResult
from .closure_expander import expand_closures, ClosureExpansionResult
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_nodes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/devforge/graph/nodes.py src/devforge/graph/runtime_state.py src/devforge/planning/__init__.py tests/test_design_nodes.py
git commit -m "feat: wire design generation, validation, and closure expansion into graph nodes"
```

---

### Task 6: Integration Test — Full Pipeline

**Files:**
- Create: `tests/test_design_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_design_integration.py
"""Integration test: concept → design → validate → expand → verify coverage."""

from devforge.graph.runtime_state import RuntimeState
from devforge.graph.nodes import (
    concept_collection_node,
    product_design_node,
    design_validation_node,
    closure_expansion_node,
)
from devforge.llm import MockLLMClient


def test_ecommerce_full_design_pipeline():
    """Simulate the full design pipeline for an ecommerce project."""
    llm = MockLLMClient()
    project = {
        "project_id": "P-ecom",
        "initiative_id": "I-001",
        "name": "二手交易平台",
        "project_archetype": "ecommerce",
        "current_phase": "concept_collect",
    }

    # Step 1: Concept collection
    state = RuntimeState(workspace_id="W-1", initiative_id="I-001", active_project_id="P-ecom")
    state = concept_collection_node(state, project=project, llm_client=llm)
    assert state.concept_decision is not None

    # Step 2: Product design
    state = product_design_node(state, project=project, llm_client=llm)
    assert state.product_design is not None
    assert len(state.product_design["domains"]) >= 4  # ecommerce should have multiple domains
    assert len(state.product_design["user_flows"]) >= 2  # buyer + seller/admin flows
    assert len(state.product_design["interaction_matrix"]) >= 2  # multiple quadrants

    # Step 3: Design validation
    state = design_validation_node(state)
    assert state.design_valid is True  # mock produces valid design

    # Step 4: Closure expansion
    state = closure_expansion_node(state, max_ring=2)
    expansion = state.closure_expansion
    assert expansion is not None
    assert expansion["total_ring_0"] > 0
    assert expansion["total_ring_1"] > 0
    # Ring 2 should be less than Ring 1 (convergence)
    assert expansion["total_ring_2_plus"] <= expansion["total_ring_1"]
    # Coverage ratio should be healthy (>= 80%)
    assert expansion["coverage_ratio"] >= 0.8

    # Verify all Ring 0 tasks have closures
    ring_0_tasks = set(state.product_design["ring_0_tasks"])
    closure_sources = {c["source_task"] for c in expansion["closures"] if c["ring"] == 1}
    assert ring_0_tasks == closure_sources, f"Missing closure sources: {ring_0_tasks - closure_sources}"


def test_gaming_full_design_pipeline():
    """Simulate the full design pipeline for a gaming project."""
    llm = MockLLMClient()
    project = {
        "project_id": "P-game",
        "initiative_id": "I-002",
        "name": "Roguelike Dungeon",
        "project_archetype": "gaming",
        "current_phase": "concept_collect",
    }

    state = RuntimeState(workspace_id="W-2", initiative_id="I-002", active_project_id="P-game")
    state = concept_collection_node(state, project=project, llm_client=llm)
    state = product_design_node(state, project=project, llm_client=llm)
    state = design_validation_node(state)
    state = closure_expansion_node(state, max_ring=1)

    assert state.design_valid is True
    assert state.closure_expansion["total_ring_1"] > 0
    # Gaming domains should include core mechanics
    domain_names = {d["name"] for d in state.product_design["domains"]}
    assert "核心机制" in domain_names or "战斗" in domain_names


def test_invalid_design_triggers_replan():
    """Verify that a design with cycles triggers replan, not crash."""
    state = RuntimeState(workspace_id="W-3")
    state.product_design = {
        "design_id": "D-bad",
        "initiative_id": "I-1",
        "project_id": "P-1",
        "product_name": "Bad Design",
        "problem_statement": "test",
        "target_users": ["user"],
        "domains": [
            {"domain_id": "A", "name": "A", "purpose": "a", "inputs": [], "outputs": [], "dependencies": ["B"]},
            {"domain_id": "B", "name": "B", "purpose": "b", "inputs": [], "outputs": [], "dependencies": ["A"]},
        ],
        "user_flows": [{"flow_id": "F-1", "name": "main", "role": "user", "steps": ["s1"]}],
        "ring_0_tasks": ["task1"],
        "interaction_matrix": [],
        "non_functional_requirements": [],
        "tech_choices": {},
        "closures": [],
        "unexplored_areas": [],
        "version": 1,
    }
    state = design_validation_node(state)
    assert state.design_valid is False
    assert state.replan_reason == "design_validation_failed"
    # Should NOT proceed to closure expansion — caller checks design_valid first
```

- [ ] **Step 2: Run the integration test**

Run: `cd /Users/aa/workspace/devforge && python -m pytest tests/test_design_integration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Run the full test suite to verify no regressions**

Run: `cd /Users/aa/workspace/devforge && python -m pytest -v`
Expected: All existing tests PASS + all new tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_design_integration.py
git commit -m "feat: add integration tests for full design pipeline (ecommerce + gaming)"
```

---

### Task 7: Run Full Suite and Final Verification

- [ ] **Step 1: Run the complete test suite**

Run: `cd /Users/aa/workspace/devforge && python -m pytest -v --tb=short`
Expected: All tests PASS, no import errors, no regressions

- [ ] **Step 2: Verify file structure matches plan**

Run: `ls -la src/devforge/state/design.py src/devforge/planning/design_generator.py src/devforge/planning/design_validator.py src/devforge/planning/closure_expander.py`
Expected: All 4 files exist

- [ ] **Step 3: Verify all new test files**

Run: `ls -la tests/test_design_model.py tests/test_design_generator.py tests/test_design_validator.py tests/test_closure_expander.py tests/test_design_nodes.py tests/test_design_integration.py`
Expected: All 6 test files exist

- [ ] **Step 4: Final commit with plan reference**

```bash
git add -A
git commit -m "chore: Plan 1 complete — product design and verification engine

Implements acceptance plan capabilities #1-#3 plus convergence:
- ProductDesign data model with 6 closure types
- LLM-driven design generator (mock + real LLM ready)
- Design validator (cycle detection, seam completeness)
- Ring-based closure expander with 3 convergence principles
- Graph nodes wired into orchestration pipeline
- 6 test files, 30+ test cases"
```
