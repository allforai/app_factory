# CLI

`devforge` can run one orchestration cycle from either a built-in fixture or an arbitrary snapshot file.

## Init

```bash
devforge init
devforge init --force
devforge init --name "My Existing Project"
devforge init --workspace
devforge init --guided
```

`init` writes starter files into `./.devforge/`:

- `./.devforge/devforge.snapshot.json`
- `./.devforge/devforge.project_config.json`

It also prepares `./.devforge/` as the default persistence root for later runs.

When run in an interactive terminal, `init` asks a small set of beginner-friendly questions for:

- AI mode
- default focus
- context size

DevForge then maps those answers into the lower-level `llm_preferences`,
`knowledge_preferences`, and `pull_policy_overrides` fields automatically.
Use `--no-prompt` to skip the questions, or `--guided` to force them on.

Use `--workspace` when the current directory is a multi-project root. DevForge will
create a guardian coordination project and register each discovered child project
that contains a common project marker such as `pyproject.toml`, `package.json`, or `go.mod`.

## Fixture

```bash
devforge fixture game_project
devforge fixture ecommerce_project --json
python -m devforge.main fixture game_project
python -m devforge.main fixture ecommerce_project --json
```

Fixture runs automatically apply a sibling `*.project_config.json` file when present.

## Snapshot

```bash
devforge snapshot ./.devforge/devforge.snapshot.json
devforge snapshot ./.devforge/devforge.snapshot.json --project-config ./.devforge/devforge.project_config.json
devforge snapshot ./.devforge/devforge.snapshot.json --persistence-root ./.devforge --json
python -m devforge.main snapshot ./.devforge/devforge.snapshot.json
python -m devforge.main snapshot ./.devforge/devforge.snapshot.json --project-config ./.devforge/devforge.project_config.json
python -m devforge.main snapshot ./.devforge/devforge.snapshot.json --persistence-root ./.devforge --json
```

`--persistence-root` creates a local runtime workspace using:

- `workspace.sqlite3`
- `artifacts/`
- `memory/`

## Output

Default output is a small summary:

```json
{
  "cycle_id": "cycle-0001",
  "active_project_id": "shop-web",
  "selected_work_packages": ["wp-cart-frontend"],
  "dispatch_count": 1,
  "result_statuses": ["completed"]
}
```

Use `--json` to print the full orchestration result.

## Live Executors

By default, executor adapters use a stub transport for local development and tests.

To let `codex` / `claude_code` run through a real local subprocess transport:

```bash
DEVFORGE_EXECUTOR_TRANSPORT=subprocess \
uv run python -m devforge.main snapshot ./.devforge/devforge.snapshot.json \
  --project-config ./.devforge/devforge.project_config.json \
  --persistence-root ./.devforge \
  --json
```

When using live subprocess transport, the executor should print a single JSON object to stdout.
`summary` is required. These keys are also supported:

- `artifacts_created`
- `artifacts_modified`
- `tests_run`
- `findings`
- `handoff_notes`
- `raw_output_ref`
