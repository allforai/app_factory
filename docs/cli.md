# CLI

`devforge` can run one orchestration cycle from either a built-in fixture or an arbitrary snapshot file.

## Init

```bash
devforge init
devforge init --force
devforge init --name "My Existing Project"
devforge init --workspace
```

`init` writes starter files into `./.devforge-runtime/`:

- `./.devforge-runtime/devforge.snapshot.json`
- `./.devforge-runtime/devforge.project_config.json`

It also prepares `./.devforge-runtime/` as the default persistence root for later runs.

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
devforge snapshot ./.devforge-runtime/devforge.snapshot.json
devforge snapshot ./.devforge-runtime/devforge.snapshot.json --project-config ./.devforge-runtime/devforge.project_config.json
devforge snapshot ./.devforge-runtime/devforge.snapshot.json --persistence-root ./.devforge-runtime --json
python -m devforge.main snapshot ./.devforge-runtime/devforge.snapshot.json
python -m devforge.main snapshot ./.devforge-runtime/devforge.snapshot.json --project-config ./.devforge-runtime/devforge.project_config.json
python -m devforge.main snapshot ./.devforge-runtime/devforge.snapshot.json --persistence-root ./.devforge-runtime --json
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
