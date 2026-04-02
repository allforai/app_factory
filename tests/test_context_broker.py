import json

from devforge.context import ContextBroker
from devforge.persistence import FileArtifactStore, JsonMemoryStore


def test_context_broker_resolves_knowledge_and_project_refs() -> None:
    snapshot = {
        "projects": [
            {
                "project_id": "p1",
                "name": "Demo",
                "project_archetype": "ecommerce",
                "current_phase": "implementation",
                "domains": ["frontend", "backend"],
            }
        ]
    }
    broker = ContextBroker(snapshot=snapshot)

    knowledge = broker.resolve_ref("domain.ecommerce", mode="summary")
    project = broker.resolve_ref("project://p1", mode="summary")

    assert knowledge.kind == "knowledge"
    assert "Commerce flow" in knowledge.content
    assert project.kind == "project"
    assert "Demo" in project.content


def test_context_broker_resolves_artifact_and_memory_refs(tmp_path) -> None:
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    memory_store = JsonMemoryStore(tmp_path / "memory")
    artifact_store.write_text("runtime/p1/concept_brief.md", "# Concept Brief\n")
    memory_store.save_memory(
        "project/p1",
        "latest-specialized-knowledge",
        json.dumps({"focus": ["ecommerce", "implementation"]}),
        metadata={"kind": "specialized_knowledge"},
    )

    broker = ContextBroker(artifact_store=artifact_store, memory_store=memory_store)
    artifact = broker.resolve_ref("artifact://runtime/p1/concept_brief.md", mode="summary")
    memory = broker.resolve_ref("memory://project/p1/latest-specialized-knowledge", mode="structured")

    assert artifact.kind == "artifact"
    assert "Concept Brief" in artifact.content
    assert memory.kind == "memory"
    assert memory.structured["metadata"]["kind"] == "specialized_knowledge"


def test_context_broker_resolve_context_bundle_applies_budget(tmp_path) -> None:
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    artifact_store.write_text("runtime/p1/concept_brief.md", "# Concept Brief\n" + ("a" * 100))
    broker = ContextBroker(artifact_store=artifact_store)

    bundle = broker.resolve_context_bundle(["artifact://runtime/p1/concept_brief.md"], mode="summary", budget=20)

    assert len(bundle) == 1
    assert bundle[0].kind == "artifact"
    assert len(bundle[0].content) <= 20
