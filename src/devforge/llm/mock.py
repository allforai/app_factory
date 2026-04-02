"""Mock LLM client for deterministic local development."""

from __future__ import annotations

from dataclasses import dataclass

from .models import StructuredGenerationRequest, StructuredGenerationResponse


@dataclass(slots=True)
class MockLLMClient:
    """Deterministic mock client used until a real provider is wired in."""

    provider_name: str = "mock"
    model_name: str = "mock-structured-v1"

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResponse:
        if request.task == "concept_collection":
            output = self._concept_output(request)
            return StructuredGenerationResponse(
                output=output,
                provider=self.provider_name,
                model=self.model_name,
                raw_text=str(output),
                metadata={"task": request.task, "schema_name": request.schema_name},
            )

        if request.task == "planning_and_shaping":
            output = self._planning_output(request)
            return StructuredGenerationResponse(
                output=output,
                provider=self.provider_name,
                model=self.model_name,
                raw_text=str(output),
                metadata={"task": request.task, "schema_name": request.schema_name},
            )

        if request.task == "product_design":
            output = self._product_design_output(request)
            return StructuredGenerationResponse(
                output=output,
                provider=self.provider_name,
                model=self.model_name,
                raw_text=str(output),
                metadata={"task": request.task, "schema_name": request.schema_name},
            )

        if request.task == "acceptance_evaluation":
            output = self._acceptance_output(request)
            return StructuredGenerationResponse(output=output, provider=self.provider_name, model=self.model_name, raw_text=str(output), metadata={"task": request.task, "schema_name": request.schema_name})

        return self._retry_output(request)

    def _concept_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        project = payload.get("project", {})
        specialized = payload.get("specialized_knowledge", {})
        focus = list(specialized.get("focus", []))
        if not focus:
            archetype = project.get("project_archetype")
            phase = project.get("current_phase")
            focus = [item for item in [archetype, phase] if item]
        name = project.get("name") or "project"
        return {
            "phase": project.get("current_phase"),
            "goal": f"collect concept model for {name}",
            "focus_areas": focus,
            "questions": [
                "What is the primary user experience or outcome?",
                "Which domains are core versus optional in the first iteration?",
            ],
            "required_artifacts": ["concept_brief.md", "acceptance_goals.json"],
            "rationale": "collect concept inputs before detailed planning and execution",
            "confidence": 0.76,
            "notes": [
                "concept decision derived from project archetype and selected knowledge",
                "focus areas limited for layered disclosure",
            ],
        }

    def _planning_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        project = payload.get("project", {})
        workset_ids = payload.get("workset_ids", [])
        packet = payload.get("node_knowledge_packet", {})
        focus = packet.get("focus", {})
        specialized = payload.get("specialized_knowledge", {})
        return {
            "selected_workset": workset_ids,
            "phase": focus.get("phase") or project.get("current_phase"),
            "goal": packet.get("brief") or project.get("name"),
            "rationale": "selected current runnable workset using project and knowledge context",
            "confidence": 0.74,
            "notes": [
                "planning decision derived from project archetype and selected knowledge",
                "specialized focus: " + ", ".join(str(item) for item in specialized.get("focus", [])[:3]),
            ],
        }

    def _product_design_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        project = payload.get("project", {})
        concept = payload.get("concept", {})
        archetype = project.get("project_archetype", "")
        name = project.get("name") or "Product"

        if archetype == "ecommerce":
            domains = [
                {"domain_id": "用户", "name": "用户", "purpose": "用户注册、认证与账户管理",
                 "inputs": ["注册信息", "登录凭证"], "outputs": ["用户令牌", "用户资料"], "dependencies": []},
                {"domain_id": "商品", "name": "商品", "purpose": "商品发布、搜索与详情展示",
                 "inputs": ["商品信息"], "outputs": ["商品列表", "商品详情"], "dependencies": ["用户"]},
                {"domain_id": "交易", "name": "交易", "purpose": "订单创建与状态流转",
                 "inputs": ["商品", "买家信息"], "outputs": ["订单"], "dependencies": ["商品", "用户"]},
                {"domain_id": "支付", "name": "支付", "purpose": "支付处理与幂等保障",
                 "inputs": ["订单"], "outputs": ["支付结果"], "dependencies": ["交易"]},
                {"domain_id": "互动", "name": "互动", "purpose": "评价、私信与社区互动",
                 "inputs": ["用户", "订单"], "outputs": ["评价", "消息"], "dependencies": ["用户", "交易"]},
                {"domain_id": "管理", "name": "管理", "purpose": "后台管理与内容审核",
                 "inputs": ["用户", "商品", "订单"], "outputs": ["审核结果", "运营报告"], "dependencies": ["用户", "商品", "交易"]},
            ]
            user_flows = [
                {"flow_id": "F-001", "name": "购买流程", "role": "buyer",
                 "steps": ["浏览", "搜索", "加购", "结算", "支付", "确认收货"],
                 "entry_point": "首页", "exit_point": "订单确认页"},
                {"flow_id": "F-002", "name": "发布流程", "role": "seller",
                 "steps": ["填写商品信息", "上传图片", "定价", "发布"],
                 "entry_point": "发布入口", "exit_point": "商品详情页"},
                {"flow_id": "F-003", "name": "审核流程", "role": "admin",
                 "steps": ["查看待审列表", "审核商品", "处理举报"],
                 "entry_point": "管理后台", "exit_point": "审核完成"},
            ]
            interaction_matrix = [
                {"feature": "浏览商品", "role": "buyer", "frequency": "high", "user_volume": "high",
                 "principle": "极致效率、零学习成本、容错性高"},
                {"feature": "用户注册", "role": "buyer", "frequency": "low", "user_volume": "high",
                 "principle": "引导式、步骤清晰"},
                {"feature": "订单审核", "role": "admin", "frequency": "high", "user_volume": "low",
                 "principle": "信息密度高、批量操作"},
                {"feature": "权限配置", "role": "admin", "frequency": "low", "user_volume": "low",
                 "principle": "安全确认、操作可撤销"},
            ]
            ring_0_tasks = ["用户注册", "商品发布", "商品搜索", "下单", "支付", "评价"]
            non_functional = ["支付幂等", "库存并发一致性", "搜索低延迟", "用户数据隔离"]
            tech_choices = {"frontend": "React", "backend": "Python/FastAPI", "database": "PostgreSQL"}
        else:
            # gaming or any other archetype
            domains = [
                {"domain_id": "核心机制", "name": "核心机制", "purpose": "游戏核心玩法循环",
                 "inputs": ["玩家输入"], "outputs": ["游戏状态"], "dependencies": []},
                {"domain_id": "地图", "name": "地图", "purpose": "场景与地形管理",
                 "inputs": ["场景配置"], "outputs": ["渲染数据"], "dependencies": ["核心机制"]},
                {"domain_id": "战斗", "name": "战斗", "purpose": "战斗逻辑与伤害结算",
                 "inputs": ["玩家行为", "敌方状态"], "outputs": ["战斗结果"], "dependencies": ["核心机制"]},
                {"domain_id": "经济", "name": "经济", "purpose": "道具、货币与奖励系统",
                 "inputs": ["战斗结果"], "outputs": ["奖励", "道具"], "dependencies": ["战斗"]},
            ]
            user_flows = [
                {"flow_id": "F-001", "name": "对战流程", "role": "player",
                 "steps": ["匹配", "进入房间", "游戏中", "结算"],
                 "entry_point": "主菜单", "exit_point": "结算页"},
            ]
            interaction_matrix = [
                {"feature": "游戏对战", "role": "player", "frequency": "high", "user_volume": "high",
                 "principle": "低延迟、响应即时"},
                {"feature": "道具购买", "role": "player", "frequency": "low", "user_volume": "high",
                 "principle": "清晰展示、防误触"},
            ]
            ring_0_tasks = ["匹配对战", "战斗结算", "道具系统", "排行榜"]
            non_functional = ["实时延迟<50ms", "高并发连接", "反作弊"]
            tech_choices = {"engine": "Unity", "backend": "Go", "networking": "WebSocket"}

        return {
            "product_name": name,
            "problem_statement": concept.get("problem_statement", f"Build {name}"),
            "target_users": list(concept.get("target_users", [])),
            "domains": domains,
            "user_flows": user_flows,
            "interaction_matrix": interaction_matrix,
            "non_functional_requirements": non_functional,
            "tech_choices": tech_choices,
            "ring_0_tasks": ring_0_tasks,
        }

    def _acceptance_output(self, request: StructuredGenerationRequest) -> dict[str, object]:
        payload = request.input_payload
        acceptance_goals: list[str] = list(payload.get("acceptance_goals", []))
        work_package_results: list[dict] = list(payload.get("work_package_results", []))
        design_summary: dict = payload.get("design_summary", {})
        closure_expansion: dict | None = payload.get("closure_expansion") or None

        # Determine overall status
        has_failures = any(
            r.get("status") in {"failed", "timed_out"} for r in work_package_results
        )
        all_completed = all(
            r.get("status") in {"completed", "verified"} for r in work_package_results
        ) if work_package_results else False

        # goal_checks
        if has_failures:
            goal_status = "unmet"
        elif all_completed:
            goal_status = "met"
        else:
            goal_status = "partial"

        goal_checks = [
            {"goal": g, "status": goal_status, "reason": f"work package evaluation: {goal_status}"}
            for g in acceptance_goals
        ]

        # gaps
        gaps: list[dict] = []
        if has_failures:
            gaps.append({
                "gap_id": "gap-mock-001",
                "description": "One or more work packages failed to complete",
                "severity": "high",
                "attributed_domain": "#11",
                "attributed_capability": "execution",
                "remediation_target": "implementation",
            })

        # role_evaluations from user_flows
        user_flows: list[dict] = list(design_summary.get("user_flows", []))
        role_evaluations: dict[str, str] = {}
        for flow in user_flows:
            role = flow.get("role")
            if role:
                role_evaluations[role] = "approved" if all_completed else "needs_review"

        # closure_density
        closure_density: dict | None = None
        if closure_expansion:
            closure_density = {
                "total_ring_0": closure_expansion.get("total_ring_0", 0),
                "covered": closure_expansion.get("total_ring_1", 0),
                "coverage_ratio": closure_expansion.get("coverage_ratio", 0.0),
            }

        is_production_ready = all_completed and not gaps
        overall_score = 0.95 if is_production_ready else 0.4

        return {
            "goal_checks": goal_checks,
            "gaps": gaps,
            "role_evaluations": role_evaluations,
            "closure_density": closure_density,
            "is_production_ready": is_production_ready,
            "overall_score": overall_score,
        }

    def _retry_output(self, request: StructuredGenerationRequest) -> StructuredGenerationResponse:
        payload = request.input_payload
        summary = str(payload.get("result", {}).get("summary", "")).lower()
        context = payload.get("context", {})
        work_package = payload.get("work_package", {})

        output = {
            "action": "requeue",
            "reason": "retry_allowed",
            "confidence": 0.72,
            "next_executor": None,
            "notes": [],
        }

        if context.get("requirement_patch_applied"):
            output |= {
                "action": "replan",
                "reason": "requirement_context_changed",
                "notes": ["recent requirement patch may invalidate implementation assumptions"],
            }
        elif ("seam" in summary or "contract" in summary) and any(
            seam.get("status") not in {"frozen", "verified"} for seam in context.get("related_seams", [])
        ):
            output |= {
                "action": "block",
                "reason": "seam_not_stable",
                "notes": ["related seam state is not stable enough for blind retry"],
            }
        elif ("rejected" in summary or len(work_package.get("execution_history", [])) >= 2) and work_package.get("fallback_executors"):
            next_executor = None
            current_executor = payload.get("result", {}).get("execution_ref", {}).get("executor") or work_package.get("executor")
            for fallback in work_package.get("fallback_executors", []):
                if fallback != current_executor:
                    next_executor = fallback
                    break
            if next_executor is not None:
                output |= {
                    "action": "switch_executor",
                    "reason": "unsupported_by_executor" if "rejected" in summary else "repeated_executor_failure",
                    "next_executor": next_executor,
                    "notes": ["executor mismatch or repeated failures suggest switching executor"],
                }

        return StructuredGenerationResponse(
            output=output,
            provider=self.provider_name,
            model=self.model_name,
            raw_text=str(output),
            metadata={"task": request.task, "schema_name": request.schema_name},
        )
