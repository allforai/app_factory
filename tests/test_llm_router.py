from devforge.llm import build_task_llm_client
from devforge.planning.concept_decision import llm_concept_collection_decider
from devforge.planning.planning_decision import llm_planning_decider
from devforge.planning.retry_decision import llm_retry_decider


def test_build_task_llm_client_uses_project_preferences_for_offline_routing() -> None:
    client = build_task_llm_client(
        task="planning_and_shaping",
        preferences={
            "provider": "openrouter",
            "planning_model": "openai/gpt-5.4-mini",
        },
    )

    assert client.provider_name == "openrouter"
    assert client.model_name == "openai/gpt-5.4-mini"


def test_project_llm_preferences_route_concept_planning_and_retry_tasks() -> None:
    preferences = {
        "provider": "openrouter",
        "concept_provider": "openrouter",
        "planning_provider": "openrouter",
        "retry_provider": "google",
        "concept_model": "anthropic/claude-sonnet-4.5",
        "planning_model": "openai/gpt-5.4-mini",
        "retry_model": "google/gemini-2.5-flash",
    }

    concept = llm_concept_collection_decider(
        project={"name": "Shop Web", "current_phase": "concept_collect", "project_archetype": "ecommerce"},
        selected_knowledge=["domain.ecommerce", "phase.concept_collect"],
        specialized_knowledge={"focus": ["ecommerce", "concept_collect"]},
        llm_preferences=preferences,
    )
    planning = llm_planning_decider(
        project={"name": "Shop Web", "current_phase": "implementation", "project_archetype": "ecommerce"},
        workset_ids=["wp-cart-frontend"],
        selected_knowledge=["domain.ecommerce", "phase.implementation"],
        specialized_knowledge={"focus": ["ecommerce", "implementation", "frontend"]},
        node_knowledge_packet={"brief": "implement cart", "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "frontend"}},
        llm_preferences=preferences,
    )
    retry = llm_retry_decider(
        {"attempt_count": 1, "max_attempts": 3, "fallback_executors": ["claude_code"]},
        {"summary": "python request rejected", "execution_ref": {"executor": "python"}},
        context={"requirement_patch_applied": False},
        llm_preferences=preferences,
    )

    assert concept.source == "openrouter:anthropic/claude-sonnet-4.5"
    assert planning.source == "openrouter:openai/gpt-5.4-mini"
    assert retry.source == "google:google/gemini-2.5-flash"
