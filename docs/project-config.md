# Project Config

Project config is a sibling JSON file named:

`<fixture>.project_config.json`

It is applied on top of the base snapshot before the orchestration cycle runs.

## Supported Keys

At the project level:

```json
{
  "projects": {
    "shop-web": {
      "llm_preferences": {},
      "knowledge_preferences": {},
      "pull_policy_overrides": []
    }
  }
}
```

## `llm_preferences`

Used by concept collection, planning, and retry routing.

Example:

```json
{
  "provider": "openrouter",
  "concept_provider": "openrouter",
  "planning_provider": "openrouter",
  "retry_provider": "google",
  "concept_model": "anthropic/claude-sonnet-4.5",
  "planning_model": "openai/gpt-5.4-mini",
  "retry_model": "google/gemini-2.5-flash"
}
```

By default, routing is offline-safe and falls back to a mock client unless live calls are explicitly enabled.

## `knowledge_preferences`

Used by knowledge selection.

Example:

```json
{
  "preferred_ids": ["phase.testing"],
  "excluded_ids": ["phase.analysis_design"]
}
```

## `pull_policy_overrides`

Used by executor context pulling.

Schema:

```json
{
  "executor": "codex",
  "mode": "summary",
  "budget": 444,
  "role_id": "software_engineer",
  "phase": "implementation",
  "project_archetype": "ecommerce",
  "ref_patterns": ["concept_brief.md", "domain.ecommerce"]
}
```

See:

- [pull_policy_overrides.example.json](/Users/aa/workspace/devforge/src/devforge/fixtures/pull_policy_overrides.example.json)
- [ecommerce_project.project_config.json](/Users/aa/workspace/devforge/src/devforge/fixtures/ecommerce_project.project_config.json)
