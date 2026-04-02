"""Tests for product design data model."""

from devforge.state.design import (
    ClosureItem,
    ClosureType,
    DomainSpec,
    InteractionMatrixEntry,
    ProductDesign,
    UserFlow,
)


def test_product_design_creation():
    design = ProductDesign(
        design_id="D-001",
        initiative_id="I-001",
        project_id="P-001",
        product_name="二手交易平台",
        problem_statement="年轻人需要一个有社区感的二手交易平台",
        target_users=["buyer", "seller", "admin"],
        domains=[
            DomainSpec(
                domain_id="商品",
                name="商品",
                purpose="管理商品发布、搜索、详情",
                inputs=["用户输入"],
                outputs=["商品列表", "商品详情"],
                dependencies=[],
            ),
        ],
        user_flows=[
            UserFlow(
                flow_id="F-001",
                name="购买流程",
                role="buyer",
                steps=["浏览", "搜索", "加购", "结算", "支付"],
                entry_point="首页",
                exit_point="订单确认页",
            ),
        ],
        interaction_matrix=[
            InteractionMatrixEntry(
                feature="浏览商品",
                role="buyer",
                frequency="high",
                user_volume="high",
                principle="极致效率、零学习成本、容错性高",
            ),
        ],
        non_functional_requirements=["支付幂等", "库存并发一致性"],
        tech_choices={"frontend": "React", "backend": "Python"},
        ring_0_tasks=["商品发布", "搜索", "下单", "支付", "评价"],
    )
    assert design.design_id == "D-001"
    assert len(design.domains) == 1
    assert len(design.user_flows) == 1
    assert len(design.interaction_matrix) == 1
    assert design.ring_0_tasks == ["商品发布", "搜索", "下单", "支付", "评价"]


def test_closure_item():
    item = ClosureItem(
        closure_id="CL-001",
        source_task="认证",
        derived_task="密码恢复",
        closure_type="exception",
        ring=1,
        rationale="认证任务的凭证丢失恢复闭环",
    )
    assert item.ring == 1
    assert item.closure_type == "exception"


def test_closure_types():
    """All six closure types must be representable."""
    types: list[ClosureType] = [
        "configuration",
        "monitoring",
        "exception",
        "permission",
        "data",
        "notification",
    ]
    for ct in types:
        item = ClosureItem(
            closure_id=f"CL-{ct}",
            source_task="任意任务",
            derived_task=f"{ct}闭环",
            closure_type=ct,
            ring=1,
            rationale=f"{ct}闭环推导",
        )
        assert item.closure_type == ct


def test_domain_spec_dependencies():
    payment = DomainSpec(
        domain_id="支付",
        name="支付",
        purpose="处理支付流程",
        inputs=["订单"],
        outputs=["支付结果"],
        dependencies=["订单"],
    )
    assert "订单" in payment.dependencies


def test_interaction_matrix_quadrants():
    """Verify the four quadrants of the interaction matrix."""
    entries = [
        InteractionMatrixEntry(
            feature="浏览", role="buyer", frequency="high", user_volume="high",
            principle="极致效率",
        ),
        InteractionMatrixEntry(
            feature="注册", role="buyer", frequency="low", user_volume="high",
            principle="引导式",
        ),
        InteractionMatrixEntry(
            feature="审核订单", role="admin", frequency="high", user_volume="low",
            principle="信息密度高",
        ),
        InteractionMatrixEntry(
            feature="权限配置", role="admin", frequency="low", user_volume="low",
            principle="安全确认",
        ),
    ]
    assert len(entries) == 4
    assert entries[0].frequency == "high" and entries[0].user_volume == "high"
    assert entries[3].frequency == "low" and entries[3].user_volume == "low"
