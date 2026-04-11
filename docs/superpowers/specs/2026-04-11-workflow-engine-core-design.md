# Design: Workflow Engine Core (Sub-project 1)

**Date:** 2026-04-11
**Scope:** `src/devforge/workflow/` (new module) + REPL integration
**Goal:** 独立 workflow 引擎，读取 `.devforge/workflows/` 目录，按节点顺序执行，追踪 artifact，写 transition log。替代 meta-skill 的 `/run` 命令，与现有 run_cycle 并存（方案 B）。

---

## 背景

DevForge 当前有两套执行机制：
- **run_cycle**：面向开发周期，基于 snapshot + work_package，适合持续迭代
- **meta-skill `/run`**：面向一次性分析工作流，基于 workflow.json + node-specs，适合 discover/reverse-concept/product-analysis 等任务

目标是把第二套能力内化到 DevForge，长期替代 meta-skill。本子项目只做引擎核心，不涉及动态节点分化（子项目 2）和内置工作流模板（子项目 3）。

---

## 方案选择

**选择方案 B：独立引擎，零破坏**

- 新建 `src/devforge/workflow/` 模块，不修改现有 run_cycle
- 现有 259 个测试不受影响
- REPL 新增 `wf` 命令组，与现有命令并存
- 为子项目 2（动态分化）和子项目 3（内置模板）预留接口

---

## 数据模型

### 目录结构

```
.devforge/workflows/
├── index.json                     # 极轻量：workflow 列表 + active_id
├── wf-<slug>-<ts>/
│   ├── manifest.json              # 节点列表（id、status、depends_on，无大字段）
│   ├── nodes/
│   │   ├── <node-id>.json         # 单节点完整定义
│   │   └── ...
│   └── transitions.jsonl          # append-only，每行一条 JSON 记录
```

**Token 加载策略：**

| 操作 | 只加载 |
|---|---|
| 引擎选下一节点 | `manifest.json` |
| 执行某节点 | `nodes/<id>.json` |
| 显示 `wf` 状态 | `manifest.json` |
| 显示 `wf log` | `transitions.jsonl` |
| 启动时 | `index.json` |

### `index.json`

```json
{
  "schema_version": "1.0",
  "active_workflow_id": "wf-逆向分析-20260411",
  "workflows": [
    {
      "id": "wf-逆向分析-20260411",
      "goal": "逆向分析 DevForge 项目",
      "status": "active",
      "created_at": "<ISO timestamp>"
    }
  ]
}
```

### `manifest.json`

```json
{
  "id": "wf-逆向分析-20260411",
  "goal": "逆向分析 DevForge 项目",
  "created_at": "<ISO timestamp>",
  "nodes": [
    {
      "id": "discover",
      "status": "completed",
      "depends_on": [],
      "exit_artifacts": [".devforge/artifacts/source-summary.json"],
      "executor": "codex",
      "parent_node_id": null,
      "depth": 0,
      "error": null
    }
  ]
}
```

### `nodes/<node-id>.json`

```json
{
  "id": "discover",
  "capability": "discovery",
  "goal": "扫描代码库，建立模块清单",
  "exit_artifacts": [".devforge/artifacts/source-summary.json"],
  "knowledge_refs": ["src/devforge/knowledge/content/capabilities/discovery.md"],
  "executor": "codex"
}
```

### `transitions.jsonl`（每行一条）

```jsonl
{"node": "discover", "status": "completed", "started_at": "...", "completed_at": "...", "artifacts_created": [".devforge/artifacts/source-summary.json"], "error": null}
```

**节点状态流转：** `pending → running → completed | failed`

**文件即真相：** 引擎启动时先检查 exit_artifacts 是否存在，存在则在 manifest 中标记 completed，优先于 transitions.jsonl 记录。

---

## 新模块结构

```
src/devforge/workflow/
├── __init__.py          # 导出 WorkflowEngine
├── models.py            # TypedDict 定义
├── engine.py            # 核心执行循环
├── store.py             # 文件读写（index/manifest/node/transitions）
└── artifacts.py         # exit_artifacts 存在性检查
```

### `models.py`

```python
from typing import TypedDict, Literal

NodeStatus = Literal["pending", "running", "completed", "failed"]
WorkflowStatus = Literal["active", "completed", "paused", "failed"]

class NodeManifestEntry(TypedDict):
    id: str
    status: NodeStatus
    depends_on: list[str]
    exit_artifacts: list[str]
    executor: str
    parent_node_id: str | None
    depth: int
    error: str | None

class NodeDefinition(TypedDict):
    id: str
    capability: str
    goal: str
    exit_artifacts: list[str]
    knowledge_refs: list[str]
    executor: str

class WorkflowManifest(TypedDict):
    id: str
    goal: str
    created_at: str
    nodes: list[NodeManifestEntry]

class WorkflowIndexEntry(TypedDict):
    id: str
    goal: str
    status: WorkflowStatus
    created_at: str

class WorkflowIndex(TypedDict):
    schema_version: str
    active_workflow_id: str | None
    workflows: list[WorkflowIndexEntry]

class TransitionEntry(TypedDict):
    node: str
    status: Literal["completed", "failed"]
    started_at: str
    completed_at: str
    artifacts_created: list[str]
    error: str | None
```

### `artifacts.py`

```python
from pathlib import Path

def check_artifacts(root: Path, paths: list[str]) -> bool:
    """全部 exit_artifacts 存在则返回 True。"""
    return all((root / p).exists() for p in paths)
```

### `store.py` 职责

- `read_index(root)` / `write_index(root, index)`
- `read_manifest(root, wf_id)` / `write_manifest(root, wf_id, manifest)`
- `read_node(root, wf_id, node_id)` / `write_node(root, wf_id, node)`
- `append_transition(root, wf_id, entry)` — append-only，不重写整个文件
- `read_transitions(root, wf_id)` — 仅 `wf log` 时调用

### `engine.py` 核心逻辑

```python
MAX_CONCURRENT = 3

def select_next_nodes(manifest: WorkflowManifest) -> list[NodeManifestEntry]:
    """选出可立即执行的节点（依赖全部 completed，且未超并发上限）。"""
    completed = {n["id"] for n in manifest["nodes"] if n["status"] == "completed"}
    running = [n for n in manifest["nodes"] if n["status"] == "running"]
    if len(running) >= MAX_CONCURRENT:
        return []
    return [
        n for n in manifest["nodes"]
        if n["status"] == "pending"
        and set(n["depends_on"]) <= completed
    ][:MAX_CONCURRENT - len(running)]

def run_one_cycle(root: Path, wf_id: str) -> dict:
    """执行一轮：选节点 → 加载定义 → 调用执行器 → 写 transitions → 更新 manifest。"""
    ...
```

---

## 引擎执行流程

```
wf run 触发一次 run_one_cycle：

1. 读 index.json → 确定 active_workflow_id
2. 读 manifest.json → 获取节点状态列表
3. 检查所有 pending/running 节点的 exit_artifacts：存在 → 更新 manifest status = completed
4. select_next_nodes(manifest) 选出可执行节点
5. 对每个选中节点：
   a. 读 nodes/<id>.json 获取完整定义（goal、knowledge_refs）
   b. 读 knowledge_refs 文件内容
   c. 构建执行器 prompt（goal + knowledge_refs + 已完成节点的 artifacts 路径）
   d. 调用 CodexAdapter（默认）或 ClaudeCodeAdapter
   e. append_transition(transitions.jsonl)
   f. 更新 manifest 中该节点的 status
6. 写回 manifest.json
7. 返回执行摘要
```

**终止条件：**
- 所有节点 `completed` → 成功，更新 index.json workflow status = completed
- 某节点 `failed` 连续 3 次 → 警告用户，停止并等待人工干预
- 无可执行节点但有 `pending` 节点 → 存在未满足依赖，报错说明哪些节点阻塞

---

## REPL 集成

### 新增命令

| 命令 | 说明 | 加载文件 |
|---|---|---|
| `wf` | 显示活跃工作流 DAG 状态 | `index.json` + `manifest.json` |
| `wf run` | 执行下一批可运行节点 | `manifest.json` + 选中节点的 `nodes/<id>.json` |
| `wf init <名称>` | 从内置模板创建工作流 | 写 `index.json` + `manifest.json` + `nodes/` |
| `wf log` | 显示执行历史 | `transitions.jsonl` |
| `wf reset <node-id>` | 重置节点为 pending | `manifest.json` |
| `wf list` | 列出所有工作流 | `index.json` |
| `wf switch <wf-id>` | 切换活跃工作流 | `index.json` |

### `wf` 输出示例

```
Workflow: 逆向分析 DevForge 项目  [wf-逆向分析-20260411]
──────────────────────────────────
✅ discover          (completed)
⏳ reverse-concept   (pending, 等待: discover)
⏳ product-analysis  (pending, 等待: reverse-concept)

进度: 1/3 节点完成
输入 'wf run' 继续执行
```

### 目标设置集成

启动时询问"当前目标"后：
- `index.json` 存在且有 active workflow → 自动显示 `wf` 状态
- 不存在 → 提示 `wf init <模板>` 创建，或 `c` 继续现有 run_cycle

---

## 文件变更

| 文件 | 变更类型 |
|---|---|
| `src/devforge/workflow/__init__.py` | 新建 |
| `src/devforge/workflow/models.py` | 新建 |
| `src/devforge/workflow/engine.py` | 新建 |
| `src/devforge/workflow/store.py` | 新建 |
| `src/devforge/workflow/artifacts.py` | 新建 |
| `src/devforge/repl.py` | 修改：新增 wf 命令解析和渲染 |
| `tests/test_workflow_engine.py` | 新建 |
| `tests/test_workflow_store.py` | 新建 |

---

## 测试策略

- **unit**：`artifacts.py` 的文件检查，`select_next_nodes()` 的依赖解析，`store.py` 的读写操作，`append_transition` 的 append-only 正确性
- **integration**：完整 workflow 从 pending → completed，失败重试逻辑，文件即真相覆盖 manifest status，多工作流切换
- **不测**：执行器实际调用（mock adapter），REPL 渲染输出

---

## 不在本子项目范围内

- 动态节点分化（子项目 2）
- 内置工作流模板 + 知识库迁移（子项目 3）
- 并发执行（顺序执行即可，并发在子项目 2 引入）
