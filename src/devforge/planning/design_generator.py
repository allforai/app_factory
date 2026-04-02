"""LLM-driven product design generator."""

from __future__ import annotations

import uuid
from typing import Any

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
    """Call the LLM with task='product_design' and return a ProductDesign dataclass."""

    llm_client = (
        llm_client
        or build_task_llm_client(task="product_design", preferences=llm_preferences)
        or MockLLMClient()
    )

    response = llm_client.generate_structured(
        StructuredGenerationRequest(
            task="product_design",
            schema_name="ProductDesign",
            instructions=(
                "You are a product architect. Generate a structured product design from the concept. "
                "Return JSON with these exact fields:\n"
                '- "product_name": (string) product name\n'
                '- "problem_statement": (string) core problem being solved\n'
                '- "target_users": (array of strings) user roles, e.g. ["buyer", "seller", "admin"]\n'
                '- "domains": (array of objects) each with {domain_id, name, purpose, inputs:[], outputs:[], dependencies:[]}\n'
                '- "user_flows": (array of objects) each with {flow_id, name, role, steps:[], entry_point, exit_point}\n'
                '- "interaction_matrix": (array of objects) each with {feature, role, frequency:"high"|"low", user_volume:"high"|"low", principle}\n'
                '- "non_functional_requirements": (array of strings) e.g. ["支付幂等", "库存并发一致性"]\n'
                '- "tech_choices": (object) e.g. {"frontend": "React", "backend": "Python"}\n'
                '- "ring_0_tasks": (array of strings) core tasks that must be implemented, e.g. ["认证", "商品发布", "搜索", "下单", "支付"]\n'
                "\nGenerate at least 3 domains, 2 user flows, 3 interaction matrix entries, and 5 ring_0_tasks."
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

    domains = [
        DomainSpec(
            domain_id=d["domain_id"],
            name=d["name"],
            purpose=d["purpose"],
            inputs=list(d.get("inputs", [])),
            outputs=list(d.get("outputs", [])),
            dependencies=list(d.get("dependencies", [])),
        )
        for d in output.get("domains", [])
    ]

    user_flows = [
        UserFlow(
            flow_id=f["flow_id"],
            name=f["name"],
            role=f["role"],
            steps=list(f.get("steps", [])),
            entry_point=f.get("entry_point", ""),
            exit_point=f.get("exit_point", ""),
        )
        for f in output.get("user_flows", [])
    ]

    interaction_matrix = [
        InteractionMatrixEntry(
            feature=e["feature"],
            role=e["role"],
            frequency=e["frequency"],
            user_volume=e["user_volume"],
            principle=e.get("principle", ""),
        )
        for e in output.get("interaction_matrix", [])
    ]

    project_id = project.get("id") or project.get("project_id") or "unknown"
    initiative_id = project.get("initiative_id") or project_id

    return ProductDesign(
        design_id=f"D-{uuid.uuid4().hex[:8]}",
        initiative_id=initiative_id,
        project_id=project_id,
        product_name=output.get("product_name", ""),
        problem_statement=output.get("problem_statement", ""),
        target_users=list(output.get("target_users", [])),
        domains=domains,
        user_flows=user_flows,
        interaction_matrix=interaction_matrix,
        non_functional_requirements=list(output.get("non_functional_requirements", [])),
        tech_choices=dict(output.get("tech_choices", {})),
        ring_0_tasks=list(output.get("ring_0_tasks", [])),
    )
