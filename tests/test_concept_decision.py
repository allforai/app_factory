from devforge.planning.concept_decision import llm_concept_collection_decider


def test_llm_concept_collection_decider_returns_structured_decision() -> None:
    decision = llm_concept_collection_decider(
        project={"name": "Game Client", "current_phase": "concept_collect", "project_archetype": "game"},
        selected_knowledge=["domain.gaming", "phase.concept_collect"],
        specialized_knowledge={"focus": ["game", "concept_collect", "worldbuilding"]},
    )

    assert decision.phase == "concept_collect"
    assert decision.goal == "collect concept model for Game Client"
    assert decision.focus_areas == ["game", "concept_collect", "worldbuilding"]
    assert decision.source == "mock:mock-structured-v1"
    assert decision.confidence == 0.76
