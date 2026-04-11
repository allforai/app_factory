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

### 状态机（两层，互相独立）

**节点状态** `NodeStatus`（`manifest.json` 中每个节点的 `status`）：

```
pending → running → completed
                 → failed  (attempt_count < 3，可重试)
                 → failed  (attempt_count >= 3，需人工介入)
```

**工作流执行状态** `WorkflowPhase`（`manifest.json` 顶层 `workflow_status`，引擎内部用）：

```
planning → awaiting_confirm → running → complete
                            ↓                  ↓
                          (user: n)        failed
                            ↓
                          planning  (重新规划)
```

**工作流生命周期状态** `WorkflowStatus`（`index.json` 中每条记录的 `status`，用户可见）：

```
active → complete | failed | paused
```

**同步规则：**
- `manifest.workflow_status == complete` → 更新 `index.status = complete`
- `manifest.workflow_status == failed`（节点失败超限）→ 更新 `index.status = failed`
- `wf switch` → 旧 active workflow 的 `index.status` 改为 `paused`
- `index.status` 不影响引擎执行，只影响 REPL 展示

---

### "文件即真相"规则及边界

- **只对普通节点生效**，`planning` 节点（`mode == "planning"`）不适用
- **`exit_artifacts == []` 时不自动 completed**，必须通过 transition 记录确认完成
- **判定标准**：文件存在且大小 > 0（不校验 JSON 格式）
- **与 transition 冲突时**：文件存在 → artifact 优先，节点标记 completed（无论 transition 记录什么）
- **`wf reset <node-id>` 后**：只重置 manifest 中的状态为 pending，不删除 artifact 文件；下次 reconcile 时若文件仍存在会再次标记 completed — **因此 reset 应配合手动删除旧 artifact 使用，文档须说明这一点**

---

## 新模块结构

```
src/devforge/workflow/
├── __init__.py          # 导出 run_one_cycle
├── models.py            # TypedDict 定义
├── engine.py            # 核心执行循环
├── store.py             # 文件读写（index/manifest/node/transitions）
├── artifacts.py         # exit_artifacts 存在性检查
└── validation.py        # workflow 合法性校验
```

### `models.py`

```python
from typing import TypedDict, Literal

NodeStatus = Literal["pending", "running", "completed", "failed"]
WorkflowPhase = Literal["planning", "awaiting_confirm", "running", "complete", "failed"]
WorkflowStatus = Literal["active", "complete", "paused", "failed"]

class NodeManifestEntry(TypedDict):
    id: str
    status: NodeStatus
    depends_on: list[str]
    exit_artifacts: list[str]
    executor: str
    mode: str | None          # None = 普通节点，"planning" = planner 节点
    parent_node_id: str | None
    depth: int
    attempt_count: int        # 累计执行次数
    last_started_at: str | None
    last_completed_at: str | None
    last_error: str | None

class NodeDefinition(TypedDict):
    id: str
    capability: str
    goal: str
    exit_artifacts: list[str]
    knowledge_refs: list[str]
    executor: str
    mode: str | None          # None | "planning"

class WorkflowManifest(TypedDict):
    id: str
    goal: str
    created_at: str
    workflow_status: WorkflowPhase
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

class PlannerOutput(TypedDict):
    nodes: list[NodeDefinition]
    summary: str
```

### `artifacts.py`

```python
from pathlib import Path

def check_artifacts(root: Path, paths: list[str]) -> bool:
    """全部 exit_artifacts 存在且非空则返回 True。"""
    return all((root / p).exists() and (root / p).stat().st_size > 0 for p in paths)
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

### 并发策略（本期）

`select_next_nodes()` 最多选 `MAX_CONCURRENT = 3` 个节点，但本期**串行 dispatch**（逐一调用执行器，等待返回后再处理下一个）。`MAX_CONCURRENT` 的存在是为子项目 2 的真并发预留接口，本期不涉及线程/进程并发。

### 主循环

```
wf run 触发一次 run_one_cycle：

1. 读 index.json → 确定 active_workflow_id（无则返回 no_active_workflow）
2. 读 manifest.json
3. 若 workflow_status == awaiting_confirm → 返回 awaiting_confirm，提示用户确认计划
4. reconcile_artifacts：对所有普通节点（mode != "planning"）且 exit_artifacts 非空，
   检查文件存在且非空 → 更新 manifest status = completed
5. select_next_nodes(manifest) 选出可执行节点（串行执行）
6. 若无可执行节点：
   - 所有节点 completed → workflow_status = complete，同步 index.status，返回 all_complete
   - 有 pending 但无 running → 返回 blocked（列出阻塞节点）
7. 对每个选中节点（串行）：
   a. mode == "planning" → 走 Planner 流程（见下）
   b. 普通节点：
      i.   更新 status = running，attempt_count += 1，last_started_at = now，写 manifest
      ii.  读 nodes/<id>.json + knowledge_refs，构建 prompt
      iii. 调用执行器（subprocess）
      iv.  exit code 0 → status = completed；非 0 → status = failed，last_error = output[:500]
      v.   更新 last_completed_at，写 manifest，append transition
      vi.  attempt_count >= 3 且 status == failed → workflow_status = failed，同步 index，停止
8. 写回 manifest.json（见原子写入策略）
9. 返回执行摘要
```

### Planner 节点流程

```
当 mode == "planning" 的节点被选中：

1. 执行执行器，期望 stdout 为 PlannerOutput JSON
2. 解析 stdout：
   - 解析失败 → status = failed，last_error = "planner output is not valid JSON: ..."
   - 解析成功：
     a. 对 PlannerOutput.nodes 做合法性校验（见校验节点）
     b. 校验失败 → status = failed，last_error = 校验错误描述
     c. 校验成功：
        - 将每个子节点写入 nodes/<id>.json（不写入 manifest.nodes）
        - 将子节点列表写入 .devforge/workflows/<wf_id>/pending_plan.json
        - planner 节点 status = completed
        - manifest.workflow_status = awaiting_confirm
        - 写 manifest，append transition
3. 返回 awaiting_confirm，REPL 展示计划并等待用户输入 y/n
```

### 用户确认流程（`wf confirm y/n`）

```
y（确认）：
  1. 读 pending_plan.json
  2. 将子节点追加到 manifest.nodes（status = pending）
  3. 删除 pending_plan.json
  4. manifest.workflow_status = running
  5. 写 manifest

n（拒绝）：
  1. 删除 pending_plan.json
  2. 删除 nodes/ 中刚写入的子节点文件
  3. planner 节点 status = pending（重新规划）
  4. manifest.workflow_status = planning
  5. 写 manifest
```

**"修改计划"功能（本期不实现）**：REPL 展示计划时不提供节点编辑入口，用户只能选 y/n。

---

## REPL 集成

### 新增命令

| 命令 | 说明 | 加载文件 |
|---|---|---|
| `wf` | 显示活跃工作流 DAG 状态 | `index.json` + `manifest.json` |
| `wf run` | 执行下一批可运行节点 | `manifest.json` + 选中节点的 `nodes/<id>.json` |
| `wf init <目标>` | 创建新工作流（含 planner 节点） | 写 `index.json` + `manifest.json` + `nodes/planner.json` |
| `wf confirm y\|n` | 确认或拒绝 planner 生成的计划 | `pending_plan.json` + `manifest.json` |
| `wf log` | 显示执行历史 | `transitions.jsonl` |
| `wf reset <node-id>` | 重置节点为 pending（须手动删旧 artifact） | `manifest.json` |
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
- 不存在 → 提示 `wf init <目标>` 创建，或 `c` 继续现有 run_cycle

---

## 非交互执行策略

节点执行过程中的人工介入是最大的可靠性风险。引擎通过两层机制消除它：

### 方案 A：非交互 prompt 规范 + 超时保底

**每个节点的 prompt 末尾统一追加以下后缀**（`_NON_INTERACTIVE_SUFFIX` 常量）：

```
---
执行约束（必须遵守）：
- 直接完成任务，不要询问任何确认或补充信息
- 若信息不足，根据已有代码和上下文做出最佳判断并继续
- 不要暂停等待用户输入
- 不要提问，不要要求审查
```

**超时机制**：`subprocess.run(..., timeout=300)`（5分钟），超时捕获 `subprocess.TimeoutExpired`，节点标记 failed，`last_error = "executor timeout after 300s"`

**执行器参数**：
- codex：`["codex", "exec", "--full-auto", "--cd", str(root), prompt + suffix]`
- claude_code：`["claude", "--print", prompt + suffix]`（`--print` 本身即非交互模式）

### 方案 B：Planner 节点预埋完整上下文

**核心原则：执行节点的 goal 必须是自包含的 — 执行器无需额外信息即可完成任务。**

Planner 节点的 goal 里包含以下约束（写入 `nodes/planner.json`）：

```
分析目标，制定执行计划。

要求：为每个子节点编写自包含的 goal，即：
- goal 中直接说明关键参数、路径、输出格式
- 不依赖执行器自行发现或询问的信息
- 示例（好）："扫描 src/devforge/ 目录，输出模块列表到 .devforge/artifacts/modules.json，格式: {modules: [{name, path, description}]}"
- 示例（差）："扫描代码库"（信息不足，执行器可能需要确认路径或格式）

输出格式（stdout JSON）：
{"nodes": [...], "summary": "..."}
```

**效果**：Planner 输出的每个子节点 goal 已经包含执行所需的全部信息，加上方案 A 的 suffix，执行器不再有理由暂停交互。

---

## 执行器 I/O 契约

### 普通节点

- **输入**：`subprocess.run(cmd, capture_output=True, text=True, timeout=300)`
  - codex：`["codex", "exec", "--full-auto", "--cd", str(root), prompt]`
  - claude_code：`["claude", "--print", prompt]`
  - `prompt` = `node.goal + "\n\n---\n\n" + knowledge_content + "\n\n" + _NON_INTERACTIVE_SUFFIX`（knowledge 为空则省略 knowledge 部分）
- **成功判定**：`returncode == 0`
- **失败时**：`last_error = (stdout or stderr)[:500]`
- **超时**：捕获 `subprocess.TimeoutExpired`，`last_error = "executor timeout after 300s"`，节点标记 failed
- **执行器不可用**（命令未找到）：捕获 `FileNotFoundError`，`last_error = "executor not found: <cmd>"`，节点标记 failed

### Planning 节点

- **输入**：同上，prompt 由 `node.goal + knowledge + _NON_INTERACTIVE_SUFFIX` 构成
  - `node.goal` 中包含对 Planner 输出格式和"自包含 goal"的要求（见非交互执行策略 · 方案 B）
- **成功判定**：`returncode == 0` 且 stdout 可解析为合法 `PlannerOutput` JSON
- **stdout 格式**：
  ```json
  {
    "nodes": [
      {
        "id": "discover",
        "capability": "discovery",
        "goal": "扫描 src/ 目录，将模块列表输出到 .devforge/artifacts/modules.json，格式：{modules:[{name,path}]}",
        "exit_artifacts": [".devforge/artifacts/modules.json"],
        "knowledge_refs": [],
        "executor": "codex",
        "mode": null
      }
    ],
    "summary": "计划说明"
  }
  ```
- **解析失败**：节点标记 failed，`last_error = "planner output parse error: <原因>"`
- **校验失败**：节点标记 failed，`last_error = "planner output validation error: <原因>"`

---

## 存储原子性策略

- **manifest.json / index.json 写入**：使用临时文件 + `os.replace(tmp, target)`（POSIX 原子操作）
- **transitions.jsonl**：append-only，Python `open(mode="a")` 本身是追加；单行 JSON 写入是原子的；读取时跳过无法解析的行（容错）
- **写入顺序**：先写 manifest → 再 append transition。若 transition 写入失败，manifest 已更新，下次 reconcile 会通过 artifact 检查恢复状态
- **多进程限制**：本期不支持多个 `wf run` 并发执行。没有 lock 文件机制，文档需说明"同一时间只运行一个 devforge 实例"

---

## 节点合法性校验（`validation.py`）

`wf init` 创建工作流时，以及 Planner 输出被接受前，均需通过校验：

- node id 在工作流内唯一
- `depends_on` 中的每个 id 必须存在于节点列表中
- 节点不能依赖自身（自依赖）
- 不存在循环依赖（DFS 检测）
- `knowledge_refs` 文件不存在时：**警告**（`stderr` 输出），不报错，执行时跳过该文件
- `executor` 必须是 `codex` 或 `claude_code`（本期支持的两种）

---

## 测试矩阵补充

除现有测试外，必须覆盖以下案例：

| 场景 | 期望行为 |
|---|---|
| depends_on 形成循环 | `validate_workflow` 抛出 `ValueError` |
| `wf reset` 后旧 artifact 仍存在 | 下次 `reconcile` 立即再次标记 completed（文档警告用户先删文件） |
| planner 输出非法 JSON | planner 节点 `status = failed`，`last_error` 包含 parse error |
| planner 输出节点 id 重复 | 校验失败，planner 节点 `status = failed` |
| `workflow_status == complete` | `index.status` 同步更新为 `complete` |
| active workflow 的 manifest 文件丢失 | `run_one_cycle` 返回 `{"status": "manifest_missing"}` |
| `transitions.jsonl` 含损坏行 | `read_transitions` 跳过损坏行，返回其余有效记录 |
| 执行器命令不存在（`FileNotFoundError`） | 节点 `status = failed`，`last_error = "executor not found: codex"` |
| 执行器超时（`TimeoutExpired`） | 节点 `status = failed`，`last_error = "executor timeout after 300s"` |
| `attempt_count >= 3` 时节点再次失败 | `workflow_status = failed`，`index.status = failed`，返回 `{"status": "workflow_failed"}` |

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
