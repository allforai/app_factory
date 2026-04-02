import json
from pathlib import Path

from app_factory.config import apply_project_config, load_project_config, maybe_apply_fixture_project_config


def test_load_project_config_reads_json(tmp_path) -> None:
    path = tmp_path / "demo.project_config.json"
    path.write_text(json.dumps({"projects": {"p1": {"llm_preferences": {"provider": "openrouter"}}}}), encoding="utf-8")

    loaded = load_project_config(path)

    assert loaded["projects"]["p1"]["llm_preferences"]["provider"] == "openrouter"


def test_apply_project_config_merges_supported_sections() -> None:
    snapshot = {
        "projects": [
            {
                "project_id": "p1",
                "llm_preferences": {},
                "knowledge_preferences": {},
                "pull_policy_overrides": [],
            }
        ]
    }
    config = {
        "projects": {
            "p1": {
                "llm_preferences": {"provider": "openrouter"},
                "knowledge_preferences": {"preferred_ids": ["phase.testing"], "excluded_ids": []},
                "pull_policy_overrides": [
                    {
                        "executor": "codex",
                        "mode": "summary",
                        "budget": 123,
                        "ref_patterns": ["concept_brief.md"],
                    }
                ],
            }
        }
    }

    updated = apply_project_config(snapshot, config)

    assert updated["projects"][0]["llm_preferences"]["provider"] == "openrouter"
    assert updated["projects"][0]["knowledge_preferences"]["preferred_ids"] == ["phase.testing"]
    assert updated["projects"][0]["pull_policy_overrides"][0]["budget"] == 123


def test_maybe_apply_fixture_project_config_uses_sibling_file(tmp_path) -> None:
    fixture_root = Path(tmp_path)
    (fixture_root / "demo.project_config.json").write_text(
        json.dumps({"projects": {"p1": {"knowledge_preferences": {"preferred_ids": ["phase.testing"], "excluded_ids": []}}}}),
        encoding="utf-8",
    )
    snapshot = {"projects": [{"project_id": "p1", "knowledge_preferences": {}}]}

    updated = maybe_apply_fixture_project_config(fixture_root, "demo", snapshot)

    assert updated["projects"][0]["knowledge_preferences"]["preferred_ids"] == ["phase.testing"]
