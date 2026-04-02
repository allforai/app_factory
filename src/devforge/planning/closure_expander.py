"""Ring-based closure expansion with convergence control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from devforge.state.design import ClosureItem, ClosureType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLOSURE_DIMENSIONS: list[ClosureType] = [
    "configuration",
    "monitoring",
    "exception",
    "permission",
    "data",
    "notification",
]

# Deterministic templates per dimension.  Each template has:
#   suffix     — appended to the source task name to form derived_task
#   rationale  — human-readable reason this closure is derived
_CLOSURE_TEMPLATES: dict[ClosureType, list[dict[str, str]]] = {
    "configuration": [
        {"suffix": "_配置管理", "rationale": "每个功能模块需要可配置的参数与开关"},
        {"suffix": "_参数校验", "rationale": "配置项加载时需要合法性校验"},
    ],
    "monitoring": [
        {"suffix": "_监控指标", "rationale": "运行时需要采集关键性能指标"},
        {"suffix": "_健康检查", "rationale": "服务需要暴露存活与就绪探针"},
    ],
    "exception": [
        {"suffix": "_异常处理", "rationale": "业务流程需要明确的错误捕获与上报"},
        {"suffix": "_重试策略", "rationale": "可恢复型失败需要幂等重试机制"},
    ],
    "permission": [
        {"suffix": "_权限校验", "rationale": "所有操作需要鉴权以保证数据安全"},
        {"suffix": "_角色绑定", "rationale": "功能访问需与角色权限挂钩"},
    ],
    "data": [
        {"suffix": "_数据模型", "rationale": "持久化层需要明确的数据结构定义"},
        {"suffix": "_数据迁移", "rationale": "Schema 演进需要版本化迁移脚本"},
    ],
    "notification": [
        {"suffix": "_事件通知", "rationale": "关键状态变化需要向相关方推送通知"},
        {"suffix": "_消息模板", "rationale": "通知内容需要可维护的模板管理"},
    ],
}

# Geometric convergence factor applied per ring level.
# Ring N items = Ring (N-1) sources × CONVERGENCE_FACTOR (floored, min 0).
_CONVERGENCE_FACTOR = 0.5


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ClosureExpansionResult:
    """Result of a Ring-based closure expansion."""

    closures: list[ClosureItem] = field(default_factory=list)
    total_ring_0: int = 0
    total_ring_1: int = 0
    total_ring_2_plus: int = 0
    coverage_ratio: float = 0.0
    stopped_reason: Literal["zero_output", "all_downgraded", "max_ring_reached"] = "max_ring_reached"
    convergence_log: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_closure_id(source_task: str, closure_type: ClosureType, ring: int, idx: int) -> str:
    """Build a deterministic, filesystem-safe closure ID."""
    safe = source_task.replace(" ", "_")
    return f"cl_r{ring}_{closure_type}_{safe}_{idx}"


def _derive_closures_for_task(
    source_task: str,
    ring: int,
    concept_boundary: list[str],  # noqa: ARG001 — kept for API symmetry
    scale_overrides: dict[str, float] | None,
) -> list[ClosureItem]:
    """Derive closures for one task across all 6 dimensions.

    The ``concept_boundary`` parameter is accepted for API symmetry but the
    boundary enforcement (filtering *sources* to those inside the boundary) is
    handled by the caller, ``expand_closures``.
    """
    items: list[ClosureItem] = []
    overrides = scale_overrides or {}

    for dim in CLOSURE_DIMENSIONS:
        templates = _CLOSURE_TEMPLATES[dim]
        for idx, tmpl in enumerate(templates):
            derived_task = f"{source_task}{tmpl['suffix']}"
            override_key = f"{source_task}:{dim}"
            scale_ratio: float = overrides.get(override_key, 1.0 / ring)

            # Scale reversal: ratio > 1.0 means the derived scope exceeds the
            # source — classify as new_domain rather than accepting.
            if scale_ratio > 1.0:
                status: Literal["proposed", "accepted", "rejected", "new_domain"] = "new_domain"
            else:
                status = "accepted"

            closure_id = _make_closure_id(source_task, dim, ring, idx)
            items.append(
                ClosureItem(
                    closure_id=closure_id,
                    source_task=source_task,
                    derived_task=derived_task,
                    closure_type=dim,
                    ring=ring,
                    rationale=tmpl["rationale"],
                    scale_ratio=scale_ratio,
                    status=status,
                )
            )
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def expand_closures(
    *,
    ring_0_tasks: list[str],
    concept_boundary: list[str],
    max_ring: int = 1,
    scale_overrides: dict[str, float] | None = None,
) -> ClosureExpansionResult:
    """Expand Ring 0 tasks into closure items using geometric convergence.

    Parameters
    ----------
    ring_0_tasks:
        The seed tasks that anchor the expansion (Ring 0).
    concept_boundary:
        Finite set of concepts within which source tasks must fall.
        Tasks outside this boundary are not used as expansion sources.
    max_ring:
        Maximum ring number to expand to (inclusive).
    scale_overrides:
        Optional mapping of ``"source_task:dimension"`` to an explicit
        scale_ratio, used to trigger scale-reversal detection in tests.

    Returns
    -------
    ClosureExpansionResult
    """
    result = ClosureExpansionResult(total_ring_0=len(ring_0_tasks))
    log = result.convergence_log

    # Ring 0 sources are the seed tasks that are inside the concept boundary.
    boundary_set = set(concept_boundary)
    current_sources: list[str] = [t for t in ring_0_tasks if t in boundary_set]

    stopped_reason: Literal["zero_output", "all_downgraded", "max_ring_reached"] = "max_ring_reached"

    # Track how many sources were available at ring 1 so we can compute the
    # geometric budget for subsequent rings.
    ring_1_source_count: int = len(current_sources)

    for ring in range(1, max_ring + 1):
        if not current_sources:
            stopped_reason = "zero_output"
            log.append(f"ring={ring}: no sources, stopping (zero_output)")
            break

        # Geometric convergence: budget for this ring is
        #   ring_1_source_count × FACTOR^(ring-1)
        # floored to an integer.  When budget reaches 0 we stop.
        budget = int(ring_1_source_count * (_CONVERGENCE_FACTOR ** (ring - 1)))
        if budget <= 0:
            stopped_reason = "zero_output"
            log.append(f"ring={ring}: budget=0, stopping (zero_output)")
            break

        # Trim current sources to the budget cap.
        active_sources = current_sources[:budget]

        ring_items: list[ClosureItem] = []
        for src in active_sources:
            ring_items.extend(
                _derive_closures_for_task(src, ring, concept_boundary, scale_overrides)
            )

        if not ring_items:
            stopped_reason = "zero_output"
            log.append(f"ring={ring}: derived zero items, stopping (zero_output)")
            break

        accepted = [c for c in ring_items if c.status == "accepted"]
        downgraded = [c for c in ring_items if c.status == "new_domain"]

        if accepted:
            result.closures.extend(ring_items)
            log.append(
                f"ring={ring}: {len(ring_items)} items "
                f"({len(accepted)} accepted, {len(downgraded)} new_domain)"
            )
        else:
            # All items were downgraded to new_domain — still add them so
            # callers can inspect them, but stop expanding.
            result.closures.extend(ring_items)
            stopped_reason = "all_downgraded"
            log.append(f"ring={ring}: all {len(ring_items)} items downgraded, stopping (all_downgraded)")
            break

        # Next ring's sources are the accepted derived tasks from this ring.
        current_sources = [c.derived_task for c in accepted]

        if ring == 1:
            result.total_ring_1 = len(ring_items)
        else:
            result.total_ring_2_plus += len(ring_items)

    else:
        stopped_reason = "max_ring_reached"
        log.append(f"max_ring={max_ring} reached")

    result.stopped_reason = stopped_reason

    # Coverage = ring_1_count / theoretical_max
    total_templates = sum(len(v) for v in _CLOSURE_TEMPLATES.values())
    theoretical_max = len(ring_0_tasks) * total_templates
    result.coverage_ratio = result.total_ring_1 / theoretical_max if theoretical_max > 0 else 0.0

    return result
