# CLI

`devforge` can run one orchestration cycle from either a built-in fixture or an arbitrary snapshot file.

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
devforge snapshot ./my_snapshot.json
devforge snapshot ./my_snapshot.json --project-config ./my_project_config.json
devforge snapshot ./my_snapshot.json --persistence-root ./.runtime --json
python -m devforge.main snapshot ./my_snapshot.json
python -m devforge.main snapshot ./my_snapshot.json --project-config ./my_project_config.json
python -m devforge.main snapshot ./my_snapshot.json --persistence-root ./.runtime --json
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
