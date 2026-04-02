from pathlib import Path

from devforge.knowledge import build_specialized_knowledge, get_knowledge_document, list_knowledge_documents, select_knowledge_for_context
from devforge.knowledge.packets import build_node_knowledge_packet


def test_knowledge_registry_points_to_local_files() -> None:
    docs = list_knowledge_documents()
    assert docs
    for doc in docs:
        assert Path(doc.path).exists()


def test_select_knowledge_for_gaming_concept_collect() -> None:
    selected = select_knowledge_for_context(
        project_archetype="gaming",
        phase="concept_collect",
    )
    selected_ids = [doc.doc_id for doc in selected]
    assert "domain.gaming" in selected_ids
    assert "phase.concept_collect" in selected_ids


def test_select_knowledge_for_frontend_implementation_prefers_testing_context() -> None:
    selected = select_knowledge_for_context(
        project_archetype="ecommerce",
        phase="implementation",
        domain="frontend",
        role_id="software_engineer",
    )
    selected_ids = [doc.doc_id for doc in selected]
    assert "domain.ecommerce" in selected_ids
    assert "phase.implementation" in selected_ids
    assert "phase.testing" in selected_ids


def test_get_knowledge_document_returns_local_migrated_doc() -> None:
    doc = get_knowledge_document("phase.analysis_design")
    assert doc.title == "Analysis and Design"


def test_build_specialized_knowledge_creates_project_specific_pack() -> None:
    specialized = build_specialized_knowledge(
        project_archetype="gaming",
        phase="implementation",
        selected_knowledge_ids=["domain.gaming", "phase.implementation"],
        domain="gameplay",
        role_id="software_engineer",
    )
    assert specialized["focus"] == ["gaming", "implementation", "gameplay", "software_engineer"]
    assert "Gaming Domain" in specialized["titles"]
    assert "Implementation" in specialized["titles"]


def test_build_node_knowledge_packet_creates_layered_disclosure() -> None:
    packet = build_node_knowledge_packet(
        phase="implementation",
        goal="Implement combat loop",
        role_id="software_engineer",
        domain="gameplay",
        specialized_knowledge={"focus": ["gaming", "implementation", "gameplay"]},
        selected_knowledge_ids=["domain.gaming", "phase.implementation"],
        constraints=["do not change seam"],
        acceptance=["combat loop playable"],
    )
    assert "implementation" in packet.brief
    assert packet.focus["phase"] == "implementation"
    assert packet.focus["role_id"] == "software_engineer"
    assert packet.focus["domain"] == "gameplay"
    assert packet.deep_refs == ["domain.gaming", "phase.implementation"]
