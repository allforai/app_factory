"""Tool-enhanced graph nodes — nodes that integrate external tools.

These wrap the base nodes from nodes.py, adding tool calls at the right points.
The base nodes remain tool-free for testing; these enhanced versions are used
in production orchestration.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from devforge.graph.runtime_state import RuntimeState
from devforge.graph import nodes as base_nodes
from devforge.llm import LLMClient


# ---------------------------------------------------------------------------
# #1 需求理解: Brave Search → concept collection
# ---------------------------------------------------------------------------

def concept_collection_with_research(
    state: RuntimeState,
    *,
    project: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    specialized_knowledge: dict[str, object] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
    brave_api_key: str | None = None,
) -> RuntimeState:
    """Concept collection with Brave Search pre-research.

    Pattern from myskills: 2-3 rounds of search per step, results become
    selection options (never open-ended questions).
    """
    proj = project or {}
    archetype = proj.get("project_archetype", "")
    name = proj.get("name", "")

    # Pre-research: 2-3 search rounds
    research_results: list[dict[str, str]] = []
    try:
        from devforge.tools.brave_search import BraveSearchClient
        search = BraveSearchClient(api_key=brave_api_key)
        if search.api_key:
            queries = _research_queries_for_archetype(name, archetype)
            for q in queries[:3]:
                for r in search.search(q, count=5, freshness="py"):
                    research_results.append({"title": r.title, "url": r.url, "snippet": r.snippet})
    except Exception:
        pass

    # Inject research into specialized knowledge
    enriched_knowledge = dict(specialized_knowledge or {})
    if research_results:
        enriched_knowledge["web_research"] = research_results[:15]
        enriched_knowledge["research_note"] = (
            "Use these search results to generate selection options. "
            "Never ask open-ended questions — always provide 2-4 evidence-based choices."
        )

    # Delegate to base node
    state = base_nodes.concept_collection_node(
        state,
        project=project,
        knowledge_ids=knowledge_ids,
        specialized_knowledge=enriched_knowledge,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )

    # Record research provenance
    if research_results:
        state.concept_decision = dict(state.concept_decision or {})
        state.concept_decision["web_research_count"] = len(research_results)

    return state


# ---------------------------------------------------------------------------
# #3 设计验证: XV multi-model audit
# ---------------------------------------------------------------------------

def design_validation_with_xv(
    state: RuntimeState,
    *,
    xv_domains: list[str] | None = None,
) -> RuntimeState:
    """Design validation with XV multi-model cross-audit.

    Pattern from myskills: different models play different roles —
    GPT audits architecture, DeepSeek audits data model, etc.
    The base validator catches structural issues; XV catches semantic issues.
    """
    # Run structural validation first
    state = base_nodes.design_validation_node(state)

    if not state.design_valid:
        return state  # structural issues must be fixed first

    # XV semantic audit
    xv_findings: list[dict[str, str]] = []
    try:
        from devforge.tools.xv_validator import XVValidator
        validator = XVValidator()
        design_json = json.dumps(state.product_design or {}, ensure_ascii=False, indent=2)
        domains = xv_domains or ["architecture_review", "data_model_review"]
        result = validator.validate("product_design", design_json, domains=domains)
        for f in result.findings:
            xv_findings.append({
                "domain": f.domain,
                "model": f.model,
                "severity": f.severity,
                "description": f.description,
                "suggestion": f.suggestion,
            })
            # Critical XV findings → design invalid
            if f.severity == "critical":
                state.design_valid = False
                state.design_validation_issues.append({
                    "error_type": f"xv_{f.domain}",
                    "message": f"[{f.model}] {f.description}",
                    "domain_ids": [],
                })
    except Exception:
        pass

    # Record XV results
    state.product_design = dict(state.product_design or {})
    state.product_design["xv_findings"] = xv_findings

    if not state.design_valid:
        state.replan_reason = "design_validation_failed"

    return state


# ---------------------------------------------------------------------------
# #2 产品设计: Brave Search + fal concept art + Stitch prompts
# ---------------------------------------------------------------------------

def product_design_with_tools(
    state: RuntimeState,
    *,
    project: dict[str, object] | None = None,
    concept: dict[str, object] | None = None,
    knowledge_ids: list[str] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
    brave_api_key: str | None = None,
    fal_api_key: str | None = None,
) -> RuntimeState:
    """Product design with search-driven decisions, concept art, and Stitch prep.

    Pattern from myskills: search for tech choices, generate concept images,
    prepare Stitch screen prompts from the design.
    """
    proj = project or {}
    name = proj.get("name", "")
    archetype = proj.get("project_archetype", "")

    # Pre-search for tech choices
    tech_research: list[dict[str, str]] = []
    try:
        from devforge.tools.brave_search import BraveSearchClient
        search = BraveSearchClient(api_key=brave_api_key)
        if search.api_key:
            for q in [f"{name} 技术架构 方案", f"{archetype} tech stack 2026"]:
                for r in search.search(q, count=3, freshness="py"):
                    tech_research.append({"title": r.title, "url": r.url, "snippet": r.snippet})
    except Exception:
        pass

    # Inject research into concept
    enriched_concept = dict(concept or state.concept_decision or {})
    if tech_research:
        enriched_concept["tech_research"] = tech_research

    # Generate design via base node
    state = base_nodes.product_design_node(
        state,
        project=project,
        concept=enriched_concept,
        knowledge_ids=knowledge_ids,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )

    design = state.product_design or {}

    # Generate concept art via fal.ai
    concept_images: list[dict[str, str]] = []
    try:
        from devforge.tools.fal_image import FalImageClient
        fal = FalImageClient(api_key=fal_api_key)
        if fal.api_key and design.get("product_name"):
            prompt = (
                f"UI concept art for {design['product_name']}, "
                f"modern mobile app interface, clean design, "
                f"target audience: young people, {archetype} category"
            )
            result = fal.generate(prompt, image_size="portrait_4_3")
            if result.success:
                concept_images.append({"url": result.image_url, "prompt": prompt})
    except Exception:
        pass

    # Prepare Stitch screen prompts
    stitch_prompts: list[dict[str, str]] = []
    try:
        from devforge.tools.stitch_ui import StitchClient
        stitch = StitchClient()
        stitch_prompts = stitch.build_prompts_from_design(design, max_screens=10)
    except Exception:
        pass

    # Attach tool results to design
    state.product_design = dict(design)
    if concept_images:
        state.product_design["concept_images"] = concept_images
    if stitch_prompts:
        state.product_design["stitch_prompts"] = stitch_prompts
    if tech_research:
        state.product_design["tech_research"] = tech_research

    return state


# ---------------------------------------------------------------------------
# #11 产品验收: XV three-party audit + Stitch visual + search benchmark
# ---------------------------------------------------------------------------

def acceptance_with_tools(
    state: RuntimeState,
    *,
    acceptance_goals: list[str] | None = None,
    work_package_results: list[dict[str, object]] | None = None,
    llm_client: LLMClient | None = None,
    llm_preferences: dict[str, object] | None = None,
    brave_api_key: str | None = None,
) -> RuntimeState:
    """Acceptance evaluation with XV multi-model audit and search benchmarks.

    Pattern from myskills: three-party audit — architecture (GPT) + UI (Gemini)
    + security (GPT), plus search for industry best practices as acceptance baseline.
    """
    design = state.product_design or {}
    product_name = design.get("product_name", "")
    archetype = design.get("project_archetype", "")

    # Search for acceptance benchmarks
    benchmark_research: list[dict[str, str]] = []
    try:
        from devforge.tools.brave_search import BraveSearchClient
        search = BraveSearchClient(api_key=brave_api_key)
        if search.api_key and product_name:
            for q in [f"{product_name} 用户体验 最佳实践", f"{archetype} acceptance criteria checklist"]:
                for r in search.search(q, count=3, freshness="py"):
                    benchmark_research.append({"title": r.title, "snippet": r.snippet})
    except Exception:
        pass

    # XV multi-model audit on work package results
    xv_audit: list[dict[str, str]] = []
    try:
        from devforge.tools.xv_validator import XVValidator
        validator = XVValidator()
        results_json = json.dumps(work_package_results or [], ensure_ascii=False)
        design_json = json.dumps(design, ensure_ascii=False)
        audit_content = f"Design:\n{design_json}\n\nResults:\n{results_json}"
        result = validator.validate(
            "acceptance_audit",
            audit_content,
            domains=["architecture_review", "ui_review", "security_review"],
        )
        for f in result.findings:
            xv_audit.append({
                "domain": f.domain,
                "model": f.model,
                "severity": f.severity,
                "description": f.description,
            })
    except Exception:
        pass

    # Inject tool results into acceptance context
    enriched_results = list(work_package_results or [])
    if benchmark_research or xv_audit:
        enriched_results.append({
            "work_package_id": "_tool_enrichment",
            "status": "completed",
            "summary": json.dumps({
                "benchmark_research": benchmark_research[:5],
                "xv_audit_findings": xv_audit,
            }, ensure_ascii=False),
        })

    # Run base acceptance
    state = base_nodes.acceptance_and_gap_check_node(
        state,
        acceptance_goals=acceptance_goals,
        work_package_results=enriched_results,
        llm_client=llm_client,
        llm_preferences=llm_preferences,
    )

    # Attach tool metadata
    if state.acceptance_verdict:
        state.acceptance_verdict = dict(state.acceptance_verdict)
        state.acceptance_verdict["xv_audit"] = xv_audit
        state.acceptance_verdict["benchmark_research_count"] = len(benchmark_research)

    return state


# ---------------------------------------------------------------------------
# #10 缝合验证: XV contract audit + demo data verification
# ---------------------------------------------------------------------------

def seam_verification_with_tools(
    seam: dict[str, Any],
    wp_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Seam verification with XV semantic audit on top of keyword matching.

    Returns enriched compliance result with XV findings.
    """
    from devforge.seams.verifier import verify_seam_compliance

    base_result = verify_seam_compliance(seam, wp_results)
    result_dict = {
        "seam_id": base_result.seam_id,
        "compliant": base_result.compliant,
        "skipped": base_result.skipped,
        "violations": [{"type": v.violation_type, "description": v.description} for v in base_result.violations],
        "criteria_met": base_result.criteria_met,
        "criteria_total": base_result.criteria_total,
    }

    # XV semantic verification
    if not base_result.skipped:
        try:
            from devforge.tools.xv_validator import XVValidator
            validator = XVValidator()
            contract_json = json.dumps(seam, ensure_ascii=False)
            results_json = json.dumps(wp_results, ensure_ascii=False)
            content = f"Contract:\n{contract_json}\n\nImplementation Results:\n{results_json}"
            xv_result = validator.validate(
                f"seam_{seam.get('seam_id', '')}",
                content,
                domains=["architecture_review"],
            )
            xv_findings = [
                {"severity": f.severity, "description": f.description}
                for f in xv_result.findings
            ]
            result_dict["xv_findings"] = xv_findings
            if any(f.severity == "critical" for f in xv_result.findings):
                result_dict["compliant"] = False
                result_dict["violations"].append({
                    "type": "xv_critical",
                    "description": "XV cross-model audit found critical contract issues",
                })
        except Exception:
            pass

    return result_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _research_queries_for_archetype(name: str, archetype: str) -> list[str]:
    """Generate research queries based on project archetype."""
    base_queries = [
        f"{name} 竞品分析",
        f"{name} 用户痛点",
    ]
    archetype_queries = {
        "ecommerce": [
            f"{name} 电商 技术架构",
            f"二手交易平台 信任机制 设计",
        ],
        "gaming": [
            f"{name} 游戏设计 核心循环",
            f"roguelike game design best practices 2026",
        ],
    }
    return base_queries + archetype_queries.get(archetype, [f"{archetype} product design patterns"])
