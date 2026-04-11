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
  "workflow_status": "planning | awaiting_confirm | running | complete | failed",
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
  "executor": "codex",
  "mode": null
}
```

`mode` 为 `null` 表示普通执行节点；`"planning"` 表示 Planner 节点，输出子节点列表而非 artifact。

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

## 集中交互模式（Human-in-the-loop Planning）

**核心设计目标：** 启动时一次性把所有问题问清楚，确认后全自动执行，中间不再打断用户。

### 流程

```
devforge 启动
  → 显示当前状态（已有 workflow → 展示进度）
  → 询问"当前目标"
  → 目标确认后，运行 Planner 节点（claude_code, mode=planning）
      Planner 输出：结构化节点列表（id/goal/executor/depends_on）
  → 引擎暂停，展示计划给用户确认：
      "准备执行以下节点，是否开始？[y/n/修改]"
      1. discover      → codex
      2. analyze       → claude_code
      3. implement     → codex
  → 用户输入 y → 创建节点 → 全自动执行至完成
  → 完成后输出汇总报告，不再询问
```

### 特殊节点类型：`planning`

`planning` 节点是工作流的入口节点，输出不是 artifact 文件，而是子节点定义列表。引擎识别到 `planning` 节点完成后，进入"等待确认"状态而非继续执行。

**`nodes/planner.json` 示例：**

```json
{
  "id": "planner",
  "capability": "planning",
  "goal": "分析目标，制定执行节点计划",
  "exit_artifacts": [],
  "knowledge_refs": [],
  "executor": "claude_code",
  "mode": "planning"
}
```

**Planner 输出格式**（stdout JSON）：

```json
{
  "nodes": [
    {
      "id": "discover",
      "capability": "discovery",
      "goal": "扫描代码库结构",
      "executor": "codex",
      "depends_on": [],
      "exit_artifacts": [".devforge/artifacts/source-summary.json"],
      "knowledge_refs": []
    }
  ],
  "summary": "计划包含 3 个节点，预计覆盖 discover → analyze → implement"
}
```

### 引擎状态扩展

`manifest.json` 新增 `workflow_status` 字段：

```json
{
  "workflow_status": "planning | awaiting_confirm | running | complete | failed"
}
```

- `planning`：Planner 节点正在执行
- `awaiting_confirm`：Planner 完成，等待用户确认节点计划
- `running`：用户确认，全自动执行中
- `complete` / `failed`：终态

### REPL 交互

确认界面（`wf run` 触发 Planner 后自动展示）：

```
Planner 已生成执行计划：
────────────────────────────────
  1. discover      codex       扫描代码库结构
  2. analyze       claude_code 分析模块依赖
  3. implement     codex       实现核心功能

输入 y 开始执行，n 取消，或输入节点编号修改：
```

用户输入 `y` 后，引擎设置 `workflow_status = running`，顺序执行所有节点，不再暂停。

### 与子项目 2 的关系

本子项目实现 Planner 节点 + 确认流程的骨架（planning 节点类型、awaiting_confirm 状态、用户确认 REPL 交互）。子项目 2 在此基础上加入运行时动态分化（节点执行过程中再次 spawn 子节点）。

---

## 不在本子项目范围内

- 运行时动态节点分化（子项目 2）——Planner 是静态预规划，子项目 2 是执行中分化
- 内置工作流模板 + 知识库迁移（子项目 3）
- 并发执行（顺序执行即可，并发在子项目 2 引入）
