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
