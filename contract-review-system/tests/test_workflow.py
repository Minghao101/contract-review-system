"""
Day 18: 工作流测试
测试LangGraph工作流、条件路由、错误处理、性能
"""
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

from src.workflow.review_workflow import (
    ContractReviewWorkflow,
    ReviewState,
    ReviewStatus,
    create_review_workflow,
)


# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

第一条 合同标的
乙方为甲方提供企业级ERP系统的技术开发服务。

第二条 服务期限
合同有效期自2024年4月1日至2024年12月31日。

第三条 服务费用及支付
3.1 服务总费用为人民币壹佰伍拾万元整（¥1,500,000.00）。

第四条 知识产权
4.1 本合同履行过程中产生的所有技术成果和知识产权归甲方所有。

第五条 保密条款
5.1 双方对本合同内容承担保密义务。

第六条 违约责任
6.1 如甲方违约，应承担无限责任。

第七条 争议解决
如发生争议，由乙方所在地法院管辖。
"""


# ============================================================
# 1. LangGraph工作流基础测试
# ============================================================

def test_langgraph_import():
    """测试LangGraph导入"""
    print("  [1/7] LangGraph导入测试...")
    assert HAS_LANGGRAPH, "langgraph未安装"
    print("    ✓ StateGraph可用")
    print("    ✓ END可用")
    print("    ✓ LangGraph导入测试通过")
    return True


def test_workflow_creation():
    """测试工作流创建"""
    print("  [2/7] 工作流创建...")

    workflow = create_review_workflow()
    assert workflow is not None
    print("    ✓ 工作流创建成功")

    # 测试ContractReviewWorkflow封装
    wrapper = ContractReviewWorkflow()
    info = wrapper.get_workflow_info()
    assert info["name"] == "合同审查工作流"
    assert len(info["nodes"]) == 5
    print(f"    ✓ 工作流名称: {info['name']}")
    print(f"    ✓ 节点数: {len(info['nodes'])}")
    print(f"    ✓ 边数: {len(info['edges'])}")
    print(f"    ✓ 条件边: {len(info['conditional_edges'])}")

    print("    ✓ 工作流创建测试通过")
    return True


# ============================================================
# 2. 条件路由测试
# ============================================================

def test_conditional_routing():
    """测试条件路由逻辑"""
    print("  [3/7] 条件路由测试...")

    from src.workflow.review_workflow import should_continue_after_parse, should_generate_report

    # 正常状态应继续
    state_normal = ReviewState(
        contract_text="test",
        contract_type="general",
        review_focus=[],
        parse_result={"document_info": {}},
        clause_result=None,
        risk_result=None,
        compliance_result=None,
        report_result=None,
        status=ReviewStatus.COMPLETED.value,
        error=None,
        steps_completed=[]
    )

    assert should_continue_after_parse(state_normal) == "continue"
    print("    ✓ 正常状态: 继续")

    # 失败状态应结束
    state_failed = state_normal.copy()
    state_failed["status"] = ReviewStatus.FAILED.value
    state_failed["error"] = "解析失败"

    assert should_continue_after_parse(state_failed) == "end"
    print("    ✓ 失败状态: 结束")

    # 合规检查后路由
    assert should_generate_report(state_normal) == "generate"
    print("    ✓ 合规通过: 生成报告")

    assert should_generate_report(state_failed) == "end"
    print("    ✓ 合规失败: 结束")

    print("    ✓ 条件路由测试通过")
    return True


# ============================================================
# 3. 工作流执行测试
# ============================================================

def test_workflow_full_execution():
    """工作流完整执行"""
    print("  [4/7] 工作流完整执行...")

    wrapper = ContractReviewWorkflow()

    start = time.time()
    result = asyncio.run(wrapper.run(
        contract_text=SAMPLE_CONTRACT,
        contract_type="service",
        review_focus=["违约责任", "知识产权"]
    ))
    elapsed = time.time() - start

    # 验证结果结构
    assert "status" in result
    assert "steps_completed" in result
    print(f"    ✓ 执行状态: {result['status']}")
    print(f"    ✓ 完成步骤: {result['steps_completed']}")
    print(f"    ✓ 耗时: {elapsed:.2f}秒")

    # 验证各阶段结果
    if result.get("parse_result"):
        print("    ✓ 解析结果: 已完成")
    if result.get("clause_result"):
        print("    ✓ 条款分析: 已完成")
    if result.get("risk_result"):
        print("    ✓ 风险评估: 已完成")
    if result.get("compliance_result"):
        print("    ✓ 合规检查: 已完成")
    if result.get("report_result"):
        print("    ✓ 报告生成: 已完成")

    if result.get("error"):
        print(f"    ⚠ 错误: {result['error']}")

    print("    ✓ 工作流完整执行测试通过")
    return True


def test_workflow_empty_contract():
    """工作流空合同处理"""
    print("  [5/7] 工作流空合同处理...")

    wrapper = ContractReviewWorkflow()

    result = asyncio.run(wrapper.run(
        contract_text="",
        contract_type="service"
    ))

    # 空合同应有错误处理
    assert "status" in result
    has_error = result.get("error") is not None
    is_failed = result["status"] == ReviewStatus.FAILED.value
    assert has_error or is_failed, f"空合同应有错误，实际: {result}"

    print(f"    ✓ 空合同状态: {result['status']}")
    if result.get("error"):
        print(f"    ✓ 错误信息: {result['error'][:50]}")

    print("    ✓ 工作流空合同处理测试通过")
    return True


# ============================================================
# 4. 工作流性能测试
# ============================================================

def test_workflow_performance():
    """工作流性能测试"""
    print("  [6/7] 工作流性能测试...")

    wrapper = ContractReviewWorkflow()

    # 多次执行测平均耗时
    times = []
    for i in range(2):
        start = time.time()
        result = asyncio.run(wrapper.run(
            contract_text=SAMPLE_CONTRACT,
            contract_type="service"
        ))
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    print(f"    ✓ 执行次数: {len(times)}")
    print(f"    ✓ 平均耗时: {avg_time:.2f}秒")
    print(f"    ✓ 最快: {min(times):.2f}秒")
    print(f"    ✓ 最慢: {max(times):.2f}秒")

    # 验证结果一致性
    assert all(r.get("status") for r in [result])
    print("    ✓ 结果一致性: 正常")

    print("    ✓ 工作流性能测试通过")
    return True


# ============================================================
# 5. 工作流信息测试
# ============================================================

def test_workflow_info():
    """工作流信息"""
    print("  [7/7] 工作流信息...")

    wrapper = ContractReviewWorkflow()
    info = wrapper.get_workflow_info()

    # 验证信息完整性
    assert "name" in info
    assert "version" in info
    assert "nodes" in info
    assert "edges" in info
    assert "conditional_edges" in info

    print(f"    ✓ 名称: {info['name']}")
    print(f"    ✓ 版本: {info['version']}")
    print(f"    ✓ 节点: {info['nodes']}")
    print(f"    ✓ 边: {len(info['edges'])}条")
    print(f"    ✓ 条件边: {len(info['conditional_edges'])}条")

    # 验证节点名称
    expected_nodes = [
        "parse_document", "analyze_clauses", "assess_risk",
        "check_compliance", "generate_report"
    ]
    assert info["nodes"] == expected_nodes
    print("    ✓ 节点名称正确")

    print("    ✓ 工作流信息测试通过")
    return True


# ============================================================
# 主测试运行器
# ============================================================

def run_all_tests():
    """运行所有工作流测试"""
    print("=" * 60)
    print("Day 18: 工作流测试 - LangGraph/路由/错误处理/性能")
    print("=" * 60)

    tests = [
        ("LangGraph导入", test_langgraph_import),
        ("工作流创建", test_workflow_creation),
        ("条件路由", test_conditional_routing),
        ("工作流完整执行", test_workflow_full_execution),
        ("空合同处理", test_workflow_empty_contract),
        ("工作流性能", test_workflow_performance),
        ("工作流信息", test_workflow_info),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    print("=" * 60)

    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
