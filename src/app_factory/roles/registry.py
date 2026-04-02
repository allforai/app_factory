"""Built-in role registry."""

from __future__ import annotations

from .specs import RoleSpec

ROLE_REGISTRY: dict[str, RoleSpec] = {
    "product_manager": RoleSpec(
        role_id="product_manager",
        name="产品经理",
        purpose="收集和澄清产品概念，定义目标、边界和验收口径",
        capabilities=["concept_discovery", "requirement_clarification", "scope_definition", "acceptance_definition", "change_management"],
        inputs=["user_input", "project_history", "initiative_context"],
        outputs=["product_concept", "requirement_events", "acceptance_goals"],
        allowed_phases=["concept_collect", "acceptance", "requirement_patch"],
        preferred_executors=["python", "claude_code"],
    ),
    "execution_planner": RoleSpec(
        role_id="execution_planner",
        name="执行策划",
        purpose="把概念转成领域结构、任务图和工作包",
        capabilities=["domain_modeling", "task_decomposition", "workflow_planning", "dependency_mapping", "project_split_planning"],
        inputs=["product_concept", "repo_context", "constraints"],
        outputs=["domain_graph", "task_graph", "work_packages"],
        allowed_phases=["concept_collect", "analysis_design", "requirement_patch"],
        preferred_executors=["python", "claude_code"],
    ),
    "interaction_designer": RoleSpec(
        role_id="interaction_designer",
        name="交互设计师",
        purpose="定义信息结构、用户路径、任务流和交互状态",
        capabilities=["information_architecture", "user_flow_design", "interaction_spec", "state_transition_design"],
        inputs=["product_concept", "domain_graph", "user_roles"],
        outputs=["user_flows", "interaction_specs", "wireframe_notes"],
        allowed_phases=["analysis_design", "requirement_patch"],
        preferred_executors=["claude_code", "opencode"],
    ),
    "ui_designer": RoleSpec(
        role_id="ui_designer",
        name="UI设计师",
        purpose="定义视觉风格、界面结构、组件规范和状态样式",
        capabilities=["visual_direction", "component_design", "screen_layout", "design_system_alignment"],
        inputs=["interaction_specs", "brand_constraints", "platform_constraints"],
        outputs=["ui_specs", "component_guidelines", "screen_mock_descriptions"],
        allowed_phases=["analysis_design", "requirement_patch"],
        preferred_executors=["claude_code", "opencode"],
    ),
    "technical_architect": RoleSpec(
        role_id="technical_architect",
        name="技术架构师",
        purpose="定义技术边界、模块拆分、共享契约和实现约束",
        capabilities=["architecture_design", "module_boundary_definition", "contract_design", "risk_analysis", "integration_strategy"],
        inputs=["product_concept", "repo_context", "domain_graph", "technical_constraints"],
        outputs=["architecture_notes", "contracts", "integration_constraints", "risk_register"],
        allowed_phases=["analysis_design", "implementation", "requirement_patch"],
        preferred_executors=["claude_code", "codex"],
    ),
    "software_engineer": RoleSpec(
        role_id="software_engineer",
        name="软件工程师",
        purpose="将设计和契约落地为代码、脚本、配置和测试",
        capabilities=["code_implementation", "refactor", "integration", "debugging", "test_authoring"],
        inputs=["repo_context", "design_specs", "contracts", "work_package_goal"],
        outputs=["code_changes", "tests", "implementation_summary"],
        allowed_phases=["analysis_design", "implementation", "testing"],
        preferred_executors=["codex", "claude_code", "cline"],
    ),
    "qa_engineer": RoleSpec(
        role_id="qa_engineer",
        name="QA测试工程师",
        purpose="验证功能正确性、边界情况、回归风险和接缝完整性",
        capabilities=["test_plan_design", "test_execution", "regression_check", "defect_reporting", "acceptance_validation"],
        inputs=["acceptance_goals", "repo_context", "contracts", "implemented_artifacts"],
        outputs=["test_results", "bug_reports", "acceptance_findings"],
        allowed_phases=["testing", "acceptance"],
        preferred_executors=["codex", "claude_code", "cline"],
    ),
    "integration_owner": RoleSpec(
        role_id="integration_owner",
        name="集成负责人",
        purpose="管理项目拆分后的接缝、契约冻结、集成验证和跨项目收敛",
        capabilities=["seam_management", "contract_freeze", "integration_validation", "cross_project_coordination", "release_readiness_check"],
        inputs=["contracts", "project_outputs", "shared_schemas", "test_results"],
        outputs=["integration_reports", "seam_findings", "release_gate_decision"],
        allowed_phases=["implementation", "testing", "acceptance", "requirement_patch"],
        preferred_executors=["python", "claude_code"],
    ),
}


def get_role_spec(role_id: str) -> RoleSpec:
    """Look up a built-in role specification."""
    return ROLE_REGISTRY[role_id]

