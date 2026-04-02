# Multi-Project Role-Driven Dev Engine Plan

## Goal

Build a Python + LangGraph orchestration engine for software development that:

- uses dynamic concept collection instead of fixed questionnaires
- organizes work through professional roles instead of raw model prompts
- dispatches chunked work packages to pluggable executors such as `claude_code`, `codex`, `cline`, and `opencode`
- supports multi-project switching, parallel execution, project split/merge, and seam governance
- keeps Python in control of concept collection, planning, acceptance, requirement patching, and project coordination

This engine is not a chat agent. It is a stateful development operating kernel.

## Design Principles

1. Separate goal, role, and executor.
2. Let Python own orchestration and state transitions.
3. Let executors own bounded analysis, design, implementation, and testing work.
4. Treat requirement change as normal input, not exception.
5. Treat seams/contracts as first-class objects after project split.
6. Prefer batch collection, batch planning, batch execution, and batch verification over frequent Q&A.
7. Use explicit artifacts and structured state instead of hidden conversational memory.

## Scope

Phase 1 focuses on the orchestration kernel and schemas:

- project and work package state model
- role system
- executor policy system
- seam and contract governance
- multi-project scheduler
- LangGraph meta workflow

Phase 1 does not require:

- full UI
- full deer-flow integration
- all executor adapters implemented
- production-grade persistence or observability

## Persistence Strategy

Persistence is layered. The orchestration kernel should not depend on a vector database for core runtime recovery.

1. State store
   Persist structured runtime state and snapshots for recovery and resume.
   Examples: `WorkspaceState`, `InitiativeState`, `ProjectState`, `WorkPackage`, `SeamState`.
   Best fit: JSON snapshot in phase 1, then SQLite or Postgres.

2. Event store
   Persist append-only execution and planning history.
   Examples: requirement events, dispatches, split operations, seam lifecycle changes.
   Best fit: JSONL or relational append log.

3. Artifact store
   Persist text artifacts and reports.
   Examples: contracts, design notes, executor reports, acceptance summaries.
   Best fit: filesystem plus metadata index.

4. Memory store
   Persist reusable memory records by namespace.
   Examples: user preferences, initiative constraints, project-specific rules, executor-specific lessons.
   Best fit: structured JSON or relational storage first.

5. Optional retrieval index
   Only add vector search for semantic recall across large memory and artifact collections.
   This is a retrieval layer, not the source of truth for orchestration state.

Runtime code should consume these stores through one grouped `WorkspacePersistence` context so orchestration entrypoints do not need to pass separate store instances around.

## Core Runtime Model

The system uses three logical layers:

1. Orchestration layer
   Python + LangGraph controls state, transitions, replanning, and acceptance.
2. Role layer
   Roles define responsibility, expected inputs/outputs, and suitable executors.
3. Executor layer
   Concrete execution backends perform delegated work packages.

Main flow:

`concept_collect -> plan_and_shape -> analysis_design -> implementation -> testing -> acceptance_and_gap_check -> requirement_patch -> repeat`

## Main State Objects

### ProjectState

Represents one active execution unit under an initiative.

Key fields:

- `project_id`
- `initiative_id`
- `parent_project_id`
- `name`
- `kind`
- `status`
- `current_phase`
- `project_archetype`
- `domains`
- `active_roles`
- `concept_model_refs`
- `contracts`
- `executor_policy_ref`
- `work_package_ids`
- `seam_ids`
- `project_memory_ref`
- `requirement_events`
- `children`

Recommended statuses:

- `active`
- `blocked`
- `waiting_input`
- `split_pending`
- `split_done`
- `archived`

### WorkPackage

Represents one bounded execution unit assigned through a role and resolved to an executor.

Key fields:

- `work_package_id`
- `project_id`
- `phase`
- `domain`
- `role_id`
- `title`
- `goal`
- `status`
- `priority`
- `executor_policy`
- `inputs`
- `deliverables`
- `constraints`
- `acceptance_criteria`
- `depends_on`
- `blocks`
- `related_seams`
- `artifacts_created`
- `findings`
- `handoff_notes`
- `attempt_count`
- `max_attempts`

Recommended statuses:

- `proposed`
- `ready`
- `running`
- `blocked`
- `waiting_review`
- `completed`
- `verified`
- `failed`
- `deprecated`

### SeamState

Represents the contract and risk surface between split projects or tightly coupled domains.

Key fields:

- `seam_id`
- `initiative_id`
- `source_project_id`
- `target_project_id`
- `type`
- `name`
- `status`
- `contract_version`
- `owner_role_id`
- `owner_executor`
- `artifacts`
- `acceptance_criteria`
- `risks`
- `related_work_packages`
- `change_log`
- `verification_refs`

Recommended statuses:

- `draft`
- `reviewing`
- `frozen`
- `implemented`
- `verified`
- `broken`
- `deprecated`

### RequirementEvent

Represents a structured product or execution change that patches existing plans.

Key fields:

- `requirement_event_id`
- `initiative_id`
- `project_ids`
- `type`
- `summary`
- `details`
- `source`
- `impact_level`
- `affected_domains`
- `affected_work_packages`
- `affected_seams`
- `patch_status`
- `created_at`
- `applied_at`

Recommended types:

- `add`
- `modify`
- `remove`
- `reprioritize`

Recommended patch statuses:

- `recorded`
- `analyzing`
- `planned`
- `applied`
- `rejected`

### ExecutorPolicy

Represents layered executor selection rules for a project or initiative.

Key fields:

- `policy_id`
- `default`
- `by_phase`
- `by_role`
- `by_domain`
- `by_work_package`
- `fallback_order`
- `rules`

Resolution priority:

`by_work_package > by_domain > by_role > by_phase > default`

Example shape:

- default executor for the project
- frontend domain mapped to `codex`
- backend domain mapped to `claude_code`
- `acceptance` phase mapped to `python`
- specific high-risk work package mapped to `claude_code`

### ExecutorResult

Represents the normalized return payload from any executor adapter.

Key fields:

- `execution_id`
- `executor`
- `work_package_id`
- `status`
- `summary`
- `artifacts_created`
- `artifacts_modified`
- `tests_run`
- `findings`
- `handoff_notes`
- `raw_output_ref`
- `started_at`
- `completed_at`

Recommended statuses:

- `completed`
- `partial`
- `failed`
- `blocked`
- `timed_out`

### InitiativeState

Represents the top-level business objective containing one or more projects.

Key fields:

- `initiative_id`
- `name`
- `goal`
- `status`
- `project_ids`
- `shared_concepts`
- `shared_contracts`
- `initiative_memory_ref`
- `global_acceptance_goals`
- `requirement_event_ids`
- `scheduler_state`

Recommended statuses:

- `active`
- `blocked`
- `in_review`
- `completed`
- `archived`

### WorkspaceState

Represents the whole operating environment, including multiple initiatives and executor capabilities.

Key fields:

- `workspace_id`
- `active_initiative_id`
- `active_project_id`
- `initiatives`
- `projects`
- `work_packages`
- `seams`
- `requirement_events`
- `executor_policies`
- `executor_registry`
- `shared_memory_ref`
- `scheduler_state`

The workspace owns the global queues for:

- ready work
- running work
- blocked work
- waiting-input work
- background projects
- foreground project

## Role System

Roles are responsibility templates, not model aliases.

Initial built-in roles:

- `product_manager`
- `execution_planner`
- `interaction_designer`
- `ui_designer`
- `technical_architect`
- `software_engineer`
- `qa_engineer`
- `integration_owner`

Each role defines:

- purpose
- capabilities
- inputs
- outputs
- allowed phases
- preferred executors

Role mapping rule:

`phase -> role bundle -> work package -> executor`

## Executor System

Executors are swappable backends:

- `python`
- `claude_code`
- `codex`
- `cline`
- `opencode`

Executor selection must support layered override:

`work_package > domain > role > phase > default`

This allows examples like:

- concept collection: `claude_code`
- frontend implementation: `codex`
- backend implementation: `claude_code`
- QA testing: `codex`
- acceptance and requirement patch: `python`

## Multi-Project Model

The engine must support one initiative containing multiple projects.

Hierarchy:

- `initiative`
- `project`
- `work_package`

Key operations:

- `project_split`
- `project_merge`
- `project_extract`
- `project_suspend`
- `project_resume`

Projects may share little context, but some memory and habits should be reusable through layered memory:

- global preference memory
- initiative memory
- project memory
- executor memory

## Requirement Change Model

Requirement change is a structured event, not informal chat drift.

The engine should patch graph state incrementally instead of regenerating the entire plan from scratch.

## Seam Governance

After project split, seams become high-risk coordination objects.

Required seam workflow:

1. define seam
2. generate contract artifacts
3. review seam
4. freeze seam
5. allow parallel implementation
6. verify seam
7. run integration tests
8. patch seam if broken

Minimum seam artifacts:

- API or schema contract
- sample payloads or mocks
- integration checklist
- acceptance cases

## LangGraph Architecture

Use a stable meta-graph to manage a dynamic task graph.

### LangGraph Runtime State

The LangGraph runtime should not mirror the full persistence layer directly.
It should hold the minimum operational state required for one orchestration cycle.

Suggested runtime state:

- `workspace_id`
- `initiative_id`
- `active_project_id`
- `current_phase`
- `phase_goal`
- `foreground_project`
- `background_projects`
- `ready_queue`
- `running_queue`
- `blocked_queue`
- `pending_requirement_events`
- `pending_seam_checks`
- `current_workset`
- `recent_executor_results`
- `replan_reason`
- `needs_user_input`
- `termination_signal`

This runtime state should reference persisted objects by id rather than embedding large documents inline whenever possible.

### Meta Graph Nodes

- `context_analysis`
- `concept_collection`
- `planning_and_shaping`
- `graph_validation`
- `batch_dispatch`
- `batch_verification`
- `acceptance_and_gap_check`
- `requirement_patch`
- `project_scheduler`

### Meta Graph Node Responsibilities

#### `project_scheduler`

Chooses the active project or initiative scope for the next orchestration round.

Responsibilities:

- pick foreground project
- decide whether a blocked project should stay blocked
- detect if background work may continue
- prioritize split coordination projects when seams are unstable

Inputs:

- workspace scheduler state
- project statuses
- queue sizes
- pending requirement events

Outputs:

- `active_project_id`
- `phase_goal`
- scheduling notes

#### `context_analysis`

Collects a batch of context before any major planning or replanning.

Responsibilities:

- gather project context
- gather repo and artifact references
- gather unresolved risks
- gather open seams and pending requirement events
- detect whether the project archetype or project boundaries changed

Outputs:

- refreshed context bundle
- discovered blockers
- project split or merge recommendation if applicable

#### `concept_collection`

Handles dynamic concept discovery and concept gap closure.

Responsibilities:

- determine which concept areas are missing
- choose concept collection role bundle
- decide if a concept node can be delegated or must remain Python-owned
- normalize collected concept artifacts

Outputs:

- updated concept model
- concept gaps
- concept completion signal

#### `planning_and_shaping`

Converts concept and context into domains, work packages, and executor assignments.

Responsibilities:

- synthesize or patch domain graph
- synthesize or patch task graph
- create work packages
- assign roles
- resolve executor policy
- detect if project split is now justified

Outputs:

- planned work packages
- dependency graph updates
- seam candidates
- batch proposal

#### `graph_validation`

Validates the plan before dispatch.

Responsibilities:

- reject invalid dependency cycles
- reject work packages without acceptance criteria
- reject risky parallel work without frozen seam or contract
- check required role coverage
- check executor assignment completeness

Outputs:

- validated workset
- validation findings
- replan signal if invalid

#### `batch_dispatch`

Dispatches a selected batch of work packages to executor adapters.

Responsibilities:

- choose runnable work packages
- respect executor concurrency limits
- respect seam constraints
- launch execution
- update work package and queue states

Outputs:

- executor dispatch records
- running queue updates

#### `batch_verification`

Collects and verifies executor results.

Responsibilities:

- normalize executor returns into `ExecutorResult`
- update work package statuses
- run acceptance checks for batch-level completion
- identify regressions, broken seams, and blocked packages

Outputs:

- verification results
- failed or partial work packages
- seam verification findings

#### `acceptance_and_gap_check`

Determines whether current project outputs satisfy intended goals.

Responsibilities:

- compare outputs against acceptance goals
- check concept-to-output closure
- identify product or technical gaps
- decide whether to finish, continue, or request requirement patching

Outputs:

- acceptance verdict
- gap list
- next action recommendation

#### `requirement_patch`

Patches the graph incrementally after requirement change or acceptance failure.

Responsibilities:

- transform requirement events into graph patches
- update affected projects, seams, and work packages
- deprecate invalid work
- preserve still-valid completed work

Outputs:

- graph patch result
- updated planning baseline
- re-entry point for next cycle

### Meta Graph Transition Rules

Recommended high-level transitions:

- `project_scheduler -> context_analysis`
- `context_analysis -> concept_collection` when concept gaps are unresolved
- `context_analysis -> planning_and_shaping` when concept state is sufficient
- `concept_collection -> planning_and_shaping` when concept artifacts are updated
- `planning_and_shaping -> graph_validation`
- `graph_validation -> planning_and_shaping` when invalid
- `graph_validation -> batch_dispatch` when valid runnable work exists
- `batch_dispatch -> batch_verification`
- `batch_verification -> acceptance_and_gap_check`
- `acceptance_and_gap_check -> requirement_patch` when requirement or closure gaps exist
- `acceptance_and_gap_check -> project_scheduler` when more work remains without patch
- `requirement_patch -> planning_and_shaping`
- any node -> `project_scheduler` when active project should switch
- any node -> terminate when `termination_signal` is set

### Dynamic Task Graph Integration

The dynamic task graph is a persisted structure managed outside the meta-graph execution loop.

The meta-graph should:

- read graph fragments relevant to the active project
- select a current workset from ready work packages
- patch the graph incrementally when requirements change
- avoid regenerating the entire graph when only one domain changes

The task graph should store:

- work package dependency edges
- seam dependencies
- executor assignment decisions
- role ownership
- batch readiness

### Workset Selection Rules

Batch selection should prefer:

1. work packages with frozen contracts
2. work packages unblocking the most downstream value
3. work packages with low overlap in file and seam risk
4. work packages aligned with currently available executors

Batch selection should avoid:

- work packages with unresolved input artifacts
- work packages depending on non-frozen seams
- multiple work packages likely to mutate the same contract or path without coordination

### Replanning Strategy

The default replanning mechanism should be graph patching, not full rewrite.

Patch operations:

- add work package
- update work package
- deprecate work package
- add seam
- update seam
- split project
- merge project
- reprioritize queues

Full graph rewrite should be reserved for:

- initiative-level pivot
- severe concept invalidation
- archetype misclassification
- failed split or merge strategy

### Task Graph

The task graph is dynamic and project-specific.

Examples:

- game projects may produce worldbuilding, combat loop, economy, narrative, art direction, prototype, playtest nodes
- ecommerce projects may produce catalog, cart, checkout, order, payment, admin, promotion, e2e nodes

The meta graph controls execution of this dynamic graph.

## Batching Strategy

The engine should avoid constant interruption.

Preferred cadence:

1. collect a batch of concept/context information
2. synthesize a batch of work packages
3. dispatch a batch of executor tasks
4. verify a batch of outputs
5. reconcile state and decide next batch

Ask the user only when:

- a key business decision is missing
- multiple valid product directions exist
- a destructive or irreversible operation needs confirmation
- a local inference would create high rework risk

## Executor Adapter Design

Executors must be hidden behind a stable Python adapter interface.

### Adapter Responsibilities

Each adapter is responsible for:

- receiving a normalized work package
- translating it into executor-specific input
- starting execution
- polling or waiting for result
- normalizing the result into `ExecutorResult`
- surfacing structured findings, artifacts, and failure modes

The orchestration layer must not depend on executor-specific prompt or response formats.

### Core Adapter Interface

Suggested interface:

```python
class ExecutorAdapter(Protocol):
    name: str

    def supports_phase(self, phase: str) -> bool: ...

    def supports_role(self, role_id: str) -> bool: ...

    def estimate(self, work_package: dict) -> dict: ...

    def dispatch(self, work_package: dict, runtime_context: dict) -> dict: ...

    def poll(self, execution_id: str) -> dict: ...

    def cancel(self, execution_id: str) -> dict: ...

    def normalize_result(self, raw_result: dict) -> dict: ...
```

### Minimal Built-In Adapters

Phase 1 should define interface stubs for:

- `PythonAdapter`
- `ClaudeCodeAdapter`
- `CodexAdapter`
- `ClineAdapter`
- `OpenCodeAdapter`

Initial implementation priority:

1. `PythonAdapter`
2. `ClaudeCodeAdapter`
3. `CodexAdapter`

### Adapter Input Contract

Every adapter should receive:

- work package metadata
- selected role context
- relevant concept references
- relevant contract and seam references
- repo paths
- constraints
- acceptance criteria
- handoff notes

Adapters may enrich the input, but they should not mutate orchestration-owned fields directly.

### Adapter Output Contract

All adapters must normalize to `ExecutorResult` and include:

- terminal status
- summary
- changed artifacts
- tests or validations performed
- blocking issues
- proposed next handoff

### Executor Selection Rules

Executor resolution order:

1. explicit work package override
2. domain rule
3. role rule
4. phase rule
5. project default
6. global fallback order

The scheduler may replace the selected executor only when:

- the executor is unavailable
- concurrency is saturated
- the phase is unsupported
- an explicit fallback rule exists

## Minimal Package Layout

Suggested initial Python package layout:

```text
app_factory/
  PLAN.md
  src/
    app_factory/
      __init__.py
      state/
        workspace.py
        initiative.py
        project.py
        work_package.py
        seam.py
        requirement_event.py
        executor_result.py
        executor_policy.py
      roles/
        specs.py
        registry.py
      executors/
        base.py
        registry.py
        python_adapter.py
        claude_code_adapter.py
        codex_adapter.py
        cline_adapter.py
        opencode_adapter.py
      graph/
        runtime_state.py
        nodes.py
        transitions.py
        builder.py
      planning/
        concept_collection.py
        task_shaping.py
        graph_patch.py
        split_merge.py
      scheduler/
        project_scheduler.py
        workset_selector.py
      seams/
        rules.py
        verification.py
      persistence/
        store.py
        json_store.py
      fixtures/
        game_project.json
        ecommerce_project.json
      main.py
  tests/
    test_state_models.py
    test_executor_policy.py
    test_workset_selector.py
    test_graph_patch.py
```

### Package Responsibilities

`state/`

- schema definitions and validation

`roles/`

- built-in role specs and role lookup

`executors/`

- adapter interfaces and executor normalization

`graph/`

- LangGraph runtime state, node logic, and graph assembly

`planning/`

- concept normalization, task shaping, patching, project split and merge logic

`scheduler/`

- active project selection and runnable workset selection

`seams/`

- seam generation, freeze rules, verification rules

`persistence/`

- storage abstraction for snapshots and fixtures

`fixtures/`

- example state documents for validation and tests

## Minimal Implementation Order

Recommended build order:

1. implement state schemas
2. implement role registry
3. implement executor policy resolution
4. implement executor adapter base interface
5. implement fixtures
6. implement workset selector
7. implement graph patch operations
8. implement LangGraph meta-graph skeleton
9. implement `PythonAdapter`
10. implement `ClaudeCodeAdapter` and `CodexAdapter`

## Planned Deliverables

### Phase 1

- state schema definitions
- role definitions
- executor policy schema
- requirement event schema
- executor result schema
- initiative and workspace schema
- seam schema
- LangGraph meta graph skeleton
- adapter interface definitions
- sample game project and ecommerce project state fixtures

### Phase 2

- executor adapters for `claude_code` and `codex`
- persistence layer
- project scheduler
- graph patch engine
- seam verification workflow

### Phase 3

- support for `cline` and `opencode`
- richer memory strategy
- UI and observability
- policy tuning and auto-splitting heuristics

## Immediate Next Steps

1. Create one game fixture and one ecommerce fixture to validate the model.
2. Define project split, merge, and seam generation rules.
3. Decide persistence format for Phase 1 fixtures and runtime snapshots.
4. Convert the state and role schema sections into Python types.
5. Draft the first pass of the executor adapter base interface in code.

## Open Questions

1. Should concept collection always start from Python prompts, or may some concept nodes be delegated immediately to an executor?
2. Should role memory be separate from executor memory, or should role outputs remain artifact-only in Phase 1?
3. When a project splits, should the parent project remain active as a coordination project by default?
4. How aggressive should automatic split detection be in Phase 1?
5. Should seam freeze be mandatory before parallel implementation in all domains, or configurable per project archetype?
