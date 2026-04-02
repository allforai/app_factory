"""Registry for migrated local knowledge documents."""

from __future__ import annotations

from pathlib import Path

from .models import KnowledgeDocument

_ROOT = Path(__file__).resolve().parent / "content"

KNOWLEDGE_REGISTRY: dict[str, KnowledgeDocument] = {
    "domain.gaming": KnowledgeDocument(
        doc_id="domain.gaming",
        title="Gaming Domain",
        category="domain",
        tags=["gaming", "worldbuilding", "economy", "progression", "narrative"],
        path=str(_ROOT / "domains" / "gaming.md"),
        summary="Game-specific concept, system, content, balance, art, and playtest guidance.",
    ),
    "domain.ecommerce": KnowledgeDocument(
        doc_id="domain.ecommerce",
        title="E-Commerce Domain",
        category="domain",
        tags=["ecommerce", "catalog", "cart", "checkout", "payment", "order"],
        path=str(_ROOT / "domains" / "ecommerce.md"),
        summary="Commerce flow, core entities, consistency rules, and checkout/order constraints.",
    ),
    "phase.concept_collect": KnowledgeDocument(
        doc_id="phase.concept_collect",
        title="Concept Collection",
        category="phase",
        tags=["concept", "problem", "roles", "validation"],
        path=str(_ROOT / "phases" / "concept_collect.md"),
        summary="Dynamic concept collection guidance from vague idea to structured concept model.",
    ),
    "phase.analysis_design": KnowledgeDocument(
        doc_id="phase.analysis_design",
        title="Analysis and Design",
        category="phase",
        tags=["design", "domain_model", "contracts", "task_shaping"],
        path=str(_ROOT / "phases" / "analysis_design.md"),
        summary="Work-package shaping, domain analysis, contract design, and architecture translation guidance.",
    ),
    "phase.implementation": KnowledgeDocument(
        doc_id="phase.implementation",
        title="Implementation",
        category="phase",
        tags=["implementation", "translation", "compile_verify", "incremental_delivery"],
        path=str(_ROOT / "phases" / "implementation.md"),
        summary="Implementation strategy selection, bounded execution, and compile-verify discipline.",
    ),
    "phase.testing": KnowledgeDocument(
        doc_id="phase.testing",
        title="Testing and Verification",
        category="phase",
        tags=["testing", "verification", "qa", "acceptance", "regression"],
        path=str(_ROOT / "phases" / "testing.md"),
        summary="Verification strategy, seam-focused QA, regression checks, and acceptance closure.",
    ),
}


def get_knowledge_document(doc_id: str) -> KnowledgeDocument:
    """Return one migrated knowledge document descriptor."""
    return KNOWLEDGE_REGISTRY[doc_id]


def list_knowledge_documents() -> list[KnowledgeDocument]:
    """List all migrated knowledge documents."""
    return list(KNOWLEDGE_REGISTRY.values())

