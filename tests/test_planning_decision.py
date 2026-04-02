from devforge.planning.planning_decision import llm_planning_decider


def test_llm_planning_decider_returns_structured_planning_decision() -> None:
    decision = llm_planning_decider(
        project={"name": "Game Client", "current_phase": "implementation", "project_archetype": "game"},
        workset_ids=["wp-combat-core"],
        selected_knowledge=["domain.gaming", "phase.implementation"],
        specialized_knowledge={"focus": ["game", "implementation", "gameplay"]},
        node_knowledge_packet={
            "brief": "implement combat prototype",
            "focus": {"phase": "implementation", "role_id": "software_engineer", "domain": "gameplay"},
        },
    )

    assert decision.selected_workset == ["wp-combat-core"]
    assert decision.phase == "implementation"
    assert decision.source == "mock:mock-structured-v1"
    assert decision.confidence == 0.74
