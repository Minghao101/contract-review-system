"""
Day 15: Agent端到端集成测试
测试Agent协作、记忆系统和工作流
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import json
from src.agents import (
    BaseAgent,
    CoordinatorAgent,
    DocumentParserAgent,
    ClauseAnalysisAgent,
    RiskAssessmentAgent,
    ComplianceCheckerAgent,
    ReportGeneratorAgent,
    MessageBus,
    AgentMessage,
    MessageType,
)
from src.agents.agent_tools import AgentTools, AgentWithTools
from src.skills import SkillRegistry, all_skills


# 测试合同文本（包含多种风险点）
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

合同编号：TS-2024-001

第一条 合同标的
乙方为甲方提供企业级ERP系统的技术开发服务，包括但不限于系统需求分析、架构设计、编码实现、系统测试和上线部署。

第二条 服务期限
合同有效期自2024年4月1日至2024年12月31日。如需延期，双方应另行协商。

第三条 服务费用及支付
3.1 服务总费用为人民币壹佰伍拾万元整（¥1,500,000.00）。
3.2 甲方应在合同签订后预付全款。
3.3 乙方应在收到款项后10个工作日内开具增值税专用发票。

第四条 验收标准
4.1 乙方应按照甲方确认的需求文档进行开发。
4.2 系统应通过甲方组织的验收测试，验收标准以甲方确认的测试用例为准。

第五条 知识产权
5.1 本合同履行过程中产生的所有技术成果和知识产权归甲方所有。
5.2 所有衍生的知识产权均归甲方所有。

第六条 保密条款
6.1 双方对本合同内容及履行过程中知悉的对方商业秘密承担保密义务。
6.2 保密期限为永久保密。
6.3 所有信息均为保密信息。

第七条 违约责任
7.1 如甲方违约，应承担无限责任，赔偿乙方一切损失。
7.2 如乙方未能按时交付，应按合同总金额的50%支付违约金。
7.3 逾期付款的，每日按逾期金额的1%支付违约金。

第八条 单方解除权
8.1 甲方可随时解除本合同，且无需承担任何违约责任。
8.2 乙方不得解除本合同。

第九条 争议解决
如发生争议，由乙方所在地法院管辖，同时双方可申请仲裁。

第十条 不可抗力
因不可抗力导致合同无法履行的，双方均不承担违约责任。

第十一条 合同终止
本合同到期后自动续约1年，除非任何一方在到期前30日书面通知不续约。
"""


# ============================================================
# 1. BaseAgent基础测试
# ============================================================

def test_base_agent():
    """测试BaseAgent基类"""
    print("  [1/8] 测试BaseAgent基类...")

    # 创建具体Agent测试基类功能
    agent = DocumentParserAgent()

    # 测试基本属性
    assert agent.agent_id == "document_parser"
    assert agent.name == "文档解析Agent"
    assert agent.role == "document_parser"
    assert not agent.is_running
    print(f"    ✓ Agent ID: {agent.agent_id}")
    print(f"    ✓ 名称: {agent.name}")
    print(f"    ✓ 角色: {agent.role}")

    # 测试状态管理
    agent.set_running(True)
    assert agent.is_running
    print("    ✓ set_running(True) 正常")

    agent.set_running(False)
    assert not agent.is_running
    print("    ✓ set_running(False) 正常")

    # 测试状态获取
    status = agent.get_status()
    assert "agent_id" in status
    assert "name" in status
    assert "role" in status
    assert "is_running" in status
    print(f"    ✓ 状态: {status}")

    # 测试私有记忆
    assert isinstance(agent.private_memory, dict)
    agent.private_memory["test_key"] = "test_value"
    assert agent.private_memory["test_key"] == "test_value"
    print("    ✓ 私有记忆读写正常")

    # 测试repr
    repr_str = repr(agent)
    assert "DocumentParserAgent" in repr_str
    print(f"    ✓ repr: {repr_str}")

    print("    ✓ BaseAgent基类测试通过")
    return True


# ============================================================
# 2. Communication模块测试
# ============================================================

def test_communication():
    """测试Agent间通信"""
    print("  [2/8] 测试Agent间通信模块...")

    bus = MessageBus()

    # 测试消息创建
    msg = AgentMessage(
        sender_id="coordinator",
        receiver_id="document_parser",
        message_type=MessageType.TASK_ASSIGN,
        content={"action": "start", "task_name": "parse_document"}
    )

    assert msg.sender_id == "coordinator"
    assert msg.receiver_id == "document_parser"
    assert msg.message_type == MessageType.TASK_ASSIGN
    print("    ✓ 消息创建正常")

    # 测试消息发布
    received_messages = []

    def on_message(message):
        received_messages.append(message)

    bus.subscribe("document_parser", on_message)
    bus.publish(msg)

    assert len(received_messages) == 1
    print("    ✓ 消息发布和订阅正常")

    # 测试广播消息
    bus.publish(AgentMessage(
        sender_id="coordinator",
        receiver_id="all",
        message_type=MessageType.TASK_RESULT,
        content={"action": "complete"}
    ))
    print("    ✓ 广播消息正常")

    # 清理
    bus.unsubscribe("document_parser", on_message)

    print("    ✓ Agent间通信测试通过")
    return True


# ============================================================
# 3. 单个Agent处理测试
# ============================================================

def test_document_parser_agent():
    """测试文档解析Agent"""
    print("  [3/8] 测试文档解析Agent...")

    agent = DocumentParserAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    result = asyncio.run(agent.process(task))

    # 检查结果结构
    assert "document_info" in result
    assert "sections" in result
    assert "dates" in result
    print(f"    ✓ 合同类型: {result['document_info'].get('contract_type', 'unknown')}")
    print(f"    ✓ 条款数: {len(result.get('sections', []))}")
    print(f"    ✓ 日期数: {len(result.get('dates', []))}")

    # 测试空文本
    result = asyncio.run(agent.process({"contract_text": ""}))
    assert "error" in result
    print("    ✓ 空文本返回错误")

    print("    ✓ 文档解析Agent测试通过")
    return True


def test_clause_analysis_agent():
    """测试条款分析Agent"""
    print("  [4/8] 测试条款分析Agent...")

    agent = ClauseAnalysisAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "review_focus": ["违约责任", "付款条款"]
    }

    result = asyncio.run(agent.process(task))

    assert "analysis" in result
    assert "completeness" in result["analysis"]
    print(f"    ✓ 完整性得分: {result['analysis']['completeness'].get('completeness_score', 0):.2%}")
    print(f"    ✓ 缺少条款: {result.get('missing_clauses', [])}")
    print(f"    ✓ 问题数量: {result.get('issues_found', 0)}")

    print("    ✓ 条款分析Agent测试通过")
    return True


def test_risk_assessment_agent():
    """测试风险评估Agent"""
    print("  [5/8] 测试风险评估Agent...")

    agent = RiskAssessmentAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    result = asyncio.run(agent.process(task))

    assert "risk_level" in result
    assert "risks" in result
    assert "risk_quantification" in result
    assert "mitigation_plan" in result
    print(f"    ✓ 风险等级: {result['risk_level']}")
    print(f"    ✓ 风险数量: {len(result.get('risks', []))}")
    print(f"    ✓ 量化分数: {result.get('risk_quantification', {}).get('risk_score', 'N/A')}")

    for risk in result.get('risks', [])[:3]:
        print(f"    ⚠ [{risk.get('severity', 'unknown')}] {risk.get('name', 'unknown')}")

    print("    ✓ 风险评估Agent测试通过")
    return True


def test_compliance_checker_agent():
    """测试合规检查Agent"""
    print("  [6/8] 测试合规检查Agent...")

    agent = ComplianceCheckerAgent()

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    result = asyncio.run(agent.process(task))

    assert "compliance_status" in result
    assert "score" in result
    print(f"    ✓ 合规状态: {result['compliance_status']}")
    print(f"    ✓ 合规分数: {result['score']}")
    print(f"    ✓ 违规数量: {len(result.get('compliance_violations', []))}")
    print(f"    ✓ 缺失条款: {result.get('missing_clauses', [])}")

    print("    ✓ 合规检查Agent测试通过")
    return True


# ============================================================
# 4. 协调器Agent测试
# ============================================================

def test_coordinator_agent():
    """测试协调器Agent"""
    print("  [7/8] 测试协调器Agent...")

    # 创建协调器
    coordinator = CoordinatorAgent()

    # 创建并注册所有Agent
    doc_parser = DocumentParserAgent()
    clause_analyst = ClauseAnalysisAgent()
    risk_assessor = RiskAssessmentAgent()
    compliance_checker = ComplianceCheckerAgent()
    report_generator = ReportGeneratorAgent()

    coordinator.register_agent(doc_parser)
    coordinator.register_agent(clause_analyst)
    coordinator.register_agent(risk_assessor)
    coordinator.register_agent(compliance_checker)
    coordinator.register_agent(report_generator)

    # 检查注册状态
    agents = coordinator.get_registered_agents()
    assert len(agents) == 5
    print(f"    ✓ 注册了 {len(agents)} 个Agent")
    for a in agents:
        print(f"      - {a['name']} ({a['role']})")

    # 测试默认执行计划
    default_plan = coordinator._get_default_plan()
    assert len(default_plan) == 5
    print(f"    ✓ 默认执行计划: {len(default_plan)} 步")

    # 测试Agent查找
    agent = coordinator._find_agent_by_role("document_parser")
    assert agent is not None
    print(f"    ✓ 查找Agent (document_parser): {agent.name}")

    agent = coordinator._find_agent_by_role("nonexistent")
    assert agent is None
    print("    ✓ 查找不存在的Agent: None")

    # 测试输入准备
    task_info = {
        "task_name": "parse_document",
        "agent_role": "document_parser",
        "input_keys": ["contract_text", "contract_type"],
        "depends_on": [],
        "parallel": False
    }
    original_task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service",
        "review_focus": ["违约责任"]
    }

    task_input = coordinator._prepare_input(task_info, original_task, SAMPLE_CONTRACT, {})
    assert "contract_text" in task_input
    assert task_input["contract_type"] == "service"
    print("    ✓ 输入准备正常")

    print("    ✓ 协调器Agent测试通过")
    return True


# ============================================================
# 5. 端到端工作流测试
# ============================================================

def test_end_to_end_workflow():
    """测试端到端工作流"""
    print("  [8/8] 测试端到端工作流...")

    # 创建协调器
    coordinator = CoordinatorAgent()

    # 注册Agent
    coordinator.register_agent(DocumentParserAgent())
    coordinator.register_agent(ClauseAnalysisAgent())
    coordinator.register_agent(RiskAssessmentAgent())
    coordinator.register_agent(ComplianceCheckerAgent())
    coordinator.register_agent(ReportGeneratorAgent())

    # 执行完整审查
    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service",
        "review_focus": ["违约责任", "知识产权"]
    }

    print("    🔄 开始执行完整审查流程...")
    result = asyncio.run(coordinator.process(task))

    # 检查结果
    assert "status" in result
    assert result["status"] in ["completed", "partial_failed"]
    print(f"    ✓ 审查状态: {result['status']}")

    # 检查各阶段结果
    sections = result.get("sections", {})
    print(f"    ✓ 完成的阶段: {list(sections.keys()) if sections else 'N/A'}")

    # 检查风险等级
    print(f"    ✓ 风险等级: {result.get('risk_level', 'unknown')}")

    # 检查合规状态
    print(f"    ✓ 合规状态: {result.get('compliance_status', 'unknown')}")

    # 检查执行计划
    if "execution_plan" in result:
        print(f"    ✓ 执行计划: {result['execution_plan']}")

    # 检查耗时
    if "elapsed_seconds" in result:
        print(f"    ✓ 耗时: {result['elapsed_seconds']:.2f}秒")

    print("    ✓ 端到端工作流测试通过")
    return True


# ============================================================
# 6. AgentTools集成测试
# ============================================================

def test_agent_tools_with_agents():
    """测试AgentTools与Agent集成"""
    print("  [附加] 测试AgentTools与Agent集成...")

    # 创建AgentTools
    tools = AgentTools()

    # 检查工具注册
    tool_list = tools.list_tools()
    assert len(tool_list) >= 12
    print(f"    ✓ 已注册 {len(tool_list)} 个工具")

    # 测试执行工具
    async def test_tool_execution():
        # 测试条款解析
        result = await tools.execute_tool("clause_parser", text=SAMPLE_CONTRACT)
        assert "total_clauses" in result
        print(f"    ✓ 条款解析: {result['total_clauses']} 个条款")

        # 测试风险识别
        result = await tools.execute_tool("risk_identifier", text=SAMPLE_CONTRACT)
        assert "total_risks" in result
        print(f"    ✓ 风险识别: {result['total_risks']} 个风险")

        # 测试法规检查
        result = await tools.execute_tool("regulation_checker", text=SAMPLE_CONTRACT)
        assert "violations_found" in result
        print(f"    ✓ 法规检查: {result['violations_found']} 个违规")

        # 测试案例检索
        result = await tools.execute_tool("case_retriever", keywords=["违约金"])
        assert "total_found" in result
        print(f"    ✓ 案例检索: {result['total_found']} 个案例")

    asyncio.run(test_tool_execution())

    print("    ✓ AgentTools与Agent集成测试通过")
    return True


def run_all_tests():
    """运行所有Agent集成测试"""
    print("=" * 60)
    print("Day 15: Agent端到端集成测试")
    print("=" * 60)

    tests = [
        ("BaseAgent基类", test_base_agent),
        ("Agent间通信", test_communication),
        ("文档解析Agent", test_document_parser_agent),
        ("条款分析Agent", test_clause_analysis_agent),
        ("风险评估Agent", test_risk_assessment_agent),
        ("合规检查Agent", test_compliance_checker_agent),
        ("协调器Agent", test_coordinator_agent),
        ("端到端工作流", test_end_to_end_workflow),
        ("AgentTools与Agent集成", test_agent_tools_with_agents),
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
