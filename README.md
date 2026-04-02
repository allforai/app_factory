# DevForge

`devforge` 是一个面向软件研发流程的 orchestration kernel。它把概念收集、规划、知识特化、执行器调度、重试、需求 patch、项目拆分、seam 治理和持久化放到同一个运行时里。

当前仓库已经具备一条最小可运行主线：

- 多项目 / 多 work package 状态管理
- 角色驱动编排
- LLM 路由与 provider 抽象
- executor payload 和按需拉取 context
- project-level config
- snapshot / event / artifact / memory 持久化
- CLI 入口

## Requirements

- Python `3.12`
- `uv`

项目当前基线见 [pyproject.toml](/Users/aa/workspace/devforge/pyproject.toml)。

## Quick Start

安装依赖并进入本地环境：

```bash
uv sync --extra dev
```

在已有项目目录里初始化 DevForge：

```bash
devforge init
devforge init --workspace
```

默认会把文件都放进 `./.devforge-runtime/`：

- `./.devforge-runtime/devforge.snapshot.json`
- `./.devforge-runtime/devforge.project_config.json`
- `./.devforge-runtime/` 作为后续运行时持久化根目录

如果当前目录本身是一个多项目 workspace，可以用 `devforge init --workspace`。
它会把当前目录初始化成一个“守护入口”项目，并自动登记一层子目录里的子项目。

直接运行内置 fixture：

```bash
devforge fixture game_project
devforge fixture ecommerce_project --json
```

也可以不用 console script，直接走模块入口：

```bash
python -m devforge.main fixture game_project
python -m devforge.main fixture ecommerce_project --json
```

## Run Your Own Snapshot

运行自己的 snapshot：

```bash
devforge snapshot ./.devforge-runtime/devforge.snapshot.json
```

给 snapshot 叠一份项目配置：

```bash
devforge snapshot ./.devforge-runtime/devforge.snapshot.json --project-config ./.devforge-runtime/devforge.project_config.json
```

启用本地持久化工作区：

```bash
devforge snapshot ./.devforge-runtime/devforge.snapshot.json --persistence-root ./.devforge-runtime --json
```

`--persistence-root` 会创建：

- `workspace.sqlite3`
- `artifacts/`
- `memory/`

## Built-in Fixtures

内置示例在 [fixtures](/Users/aa/workspace/devforge/src/devforge/fixtures)：

- [game_project.json](/Users/aa/workspace/devforge/src/devforge/fixtures/game_project.json)
- [ecommerce_project.json](/Users/aa/workspace/devforge/src/devforge/fixtures/ecommerce_project.json)
- [ecommerce_project.project_config.json](/Users/aa/workspace/devforge/src/devforge/fixtures/ecommerce_project.project_config.json)

fixture 运行时，如果旁边存在同名 `*.project_config.json`，会自动加载。

## Project Config

项目配置用于覆写单个项目的运行偏好，目前支持三类：

- `llm_preferences`
- `knowledge_preferences`
- `pull_policy_overrides`

最小结构：

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

例子见：

- [project-config.md](/Users/aa/workspace/devforge/docs/project-config.md)
- [ecommerce_project.project_config.json](/Users/aa/workspace/devforge/src/devforge/fixtures/ecommerce_project.project_config.json)

## CLI Output

默认输出是摘要：

```json
{
  "cycle_id": "cycle-0001",
  "active_project_id": "shop-web",
  "selected_work_packages": ["wp-cart-frontend"],
  "dispatch_count": 1,
  "result_statuses": ["completed"]
}
```

加 `--json` 会输出完整 orchestration result。

## How It Is Organized

最值得先看的目录：

- [src/devforge/main.py](/Users/aa/workspace/devforge/src/devforge/main.py)
  CLI 和运行入口
- [src/devforge/graph](/Users/aa/workspace/devforge/src/devforge/graph)
  orchestration graph 和 runtime
- [src/devforge/llm](/Users/aa/workspace/devforge/src/devforge/llm)
  LLM provider / transport / routing
- [src/devforge/executors](/Users/aa/workspace/devforge/src/devforge/executors)
  executor adapter、payload、pull policy
- [src/devforge/knowledge](/Users/aa/workspace/devforge/src/devforge/knowledge)
  本地知识库、选择、特化、节点知识包
- [src/devforge/persistence](/Users/aa/workspace/devforge/src/devforge/persistence)
  snapshot / event / artifact / memory store

## Docs

- [docs/cli.md](/Users/aa/workspace/devforge/docs/cli.md)
- [docs/project-config.md](/Users/aa/workspace/devforge/docs/project-config.md)
- [PLAN.md](/Users/aa/workspace/devforge/PLAN.md)

## Test

```bash
UV_CACHE_DIR=/Users/aa/workspace/devforge/.uv-cache uv run --with pytest pytest -q
```

最近一次结果：`98 passed`
