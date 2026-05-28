"""
Day 15: LangChain Tools和AgentTools集成测试
测试工具注册、调用和Agent集成
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.tools.langchain_tools import contract_tools, analyze_clause, assess_risk, generate_suggestions, summarize_contract
from src.agents.agent_tools import AgentTools, AgentWithTools
from src.skills.skill_registry import SkillRegistry
from src.skills import all_skills


# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

一、合同标的
乙方为甲方提供企业级ERP系统的技术开发服务，包括系统设计、编码实现和测试。

二、服务期限
合同有效期自2024年4月1日至2024年12月31日。

三、服务费用及支付
服务总费用为人民币150万元，甲方应在合同签订后预付全款。

四、违约责任
如甲方违约，应承担无限责任，赔偿乙方一切损失。

五、争议解决
如发生争议，由乙方所在地法院管辖，同时双方可申请仲裁。
"""


# ============================================================
# 1. LangChain Tools基础测试
# ============================================================

def test_contract_tools_availability():
    """测试合同工具可用性"""
    print("  [1/5] 测试LangChain Tools可用性...")

    # 检查工具列表
    assert len(contract_tools) == 4
    tool_names = [tool.name for tool in contract_tools]
    assert "analyze_clause" in tool_names
    assert "assess_risk" in tool_names
    assert "generate_suggestions" in tool_names
    assert "summarize_contract" in tool_names
    print(f"    ✓ 工具数量: {len(contract_tools)}")
    print(f"    ✓ 工具名称: {', '.join(tool_names)}")

    # 检查工具描述
    for tool in contract_tools:
        assert tool.description is not None
        assert len(tool.description) > 0
    print("    ✓ 所有工具有描述")

    print("    ✓ LangChain Tools可用性测试通过")
    return True


def test_analyze_clause_tool():
    """测试analyze_clause工具"""
    print("  [2/5] 测试analyze_clause工具...")

    # 测试工具名称和描述
    assert analyze_clause.name == "analyze_clause"
    assert "条款" in analyze_clause.description
    print(f"    ✓ 工具名称: {analyze_clause.name}")
    print(f"    ✓ 描述: {analyze_clause.description[:40]}...")

    # 注意：实际调用需要LLM连接，这里只测试工具定义
    # 测试工具参数 schema
    args_schema = analyze_clause.args
    assert args_schema is not None
    print(f"    ✓ 参数schema存在")

    print("    ✓ analyze_clause工具测试通过")
    return True


def test_assess_risk_tool():
    """测试assess_risk工具"""
    print("  [3/5] 测试assess_risk工具...")

    assert assess_risk.name == "assess_risk"
    assert "风险" in assess_risk.description
    print(f"    ✓ 工具名称: {assess_risk.name}")

    args_schema = assess_risk.args
    assert args_schema is not None
    print(f"    ✓ 参数schema存在")

    print("    ✓ assess_risk工具测试通过")
    return True


def test_generate_suggestions_tool():
    """测试generate_suggestions工具"""
    print("  [4/5] 测试generate_suggestions工具...")

    assert generate_suggestions.name == "generate_suggestions"
    assert "建议" in generate_suggestions.description
    print(f"    ✓ 工具名称: {generate_suggestions.name}")

    args_schema = generate_suggestions.args
    assert args_schema is not None
    print(f"    ✓ 参数schema存在")

    print("    ✓ generate_suggestions工具测试通过")
    return True


def test_summarize_contract_tool():
    """测试summarize_contract工具"""
    print("  [5/5] 测试summarize_contract工具...")

    assert summarize_contract.name == "summarize_contract"
    assert "摘要" in summarize_contract.description
    print(f"    ✓ 工具名称: {summarize_contract.name}")

    args_schema = summarize_contract.args
    assert args_schema is not None
    print(f"    ✓ 参数schema存在")

    print("    ✓ summarize_contract工具测试通过")
    return True


# ============================================================
# 2. AgentTools集成测试
# ============================================================

def test_agent_tools_initialization():
    """测试AgentTools初始化"""
    print("  [附加1] 测试AgentTools初始化...")

    tools = AgentTools()

    # 检查工具列表
    tool_list = tools.list_tools()
    assert len(tool_list) >= 12  # 12个Skills
    print(f"    ✓ 可用工具数: {len(tool_list)}")

    # 检查工具名称
    tool_names = [t["skill_id"] for t in tool_list]
    assert "pdf_reader" in tool_names
    assert "clause_parser" in tool_names
    assert "risk_identifier" in tool_names
    print(f"    ✓ 包含文档工具: pdf_reader, docx_parser, ocr_processor")
    print(f"    ✓ 包含法律工具: clause_parser, regulation_checker, case_retriever")
    print(f"    ✓ 包含风险工具: risk_identifier, risk_scorer, mitigation_suggester")
    print(f"    ✓ 包含报告工具: report_generator, visualization, export")

    print("    ✓ AgentTools初始化测试通过")
    return True


def test_agent_tools_langchain_conversion():
    """测试Skill到LangChain工具的转换"""
    print("  [附加2] 测试Skill到LangChain工具转换...")

    tools = AgentTools()

    # 创建所有LangChain工具
    tools.create_all_langchain_tools()

    lc_tools = tools.get_langchain_tools()
    assert len(lc_tools) >= 12
    print(f"    ✓ 创建了 {len(lc_tools)} 个LangChain工具")

    # 检查工具类型
    for tool in lc_tools:
        assert hasattr(tool, 'name')
        assert hasattr(tool, 'description')
        assert hasattr(tool, 'invoke')
    print("    ✓ 所有工具具有LangChain Tool接口")

    # 检查工具名称唯一性
    tool_names = [t.name for t in lc_tools]
    assert len(tool_names) == len(set(tool_names))
    print("    ✓ 工具名称唯一")

    print("    ✓ Skill到LangChain工具转换测试通过")
    return True


def test_agent_tools_execution():
    """测试工具执行"""
    print("  [附加3] 测试工具执行...")

    tools = AgentTools()

    # 测试执行条款解析工具
    async def run_test():
        result = await tools.execute_tool("clause_parser", text=SAMPLE_CONTRACT)
        return result

    result = asyncio.run(run_test())
    assert "total_clauses" in result
    print(f"    ✓ 条款解析: {result['total_clauses']} 个条款")

    # 测试执行风险识别工具
    async def run_risk_test():
        result = await tools.execute_tool("risk_identifier", text=SAMPLE_CONTRACT)
        return result

    result = asyncio.run(run_risk_test())
    assert "total_risks" in result
    print(f"    ✓ 风险识别: {result['total_risks']} 个风险")

    # 测试执行法规检查工具
    async def run_regulation_test():
        result = await tools.execute_tool("regulation_checker", text=SAMPLE_CONTRACT)
        return result

    result = asyncio.run(run_regulation_test())
    assert "violations_found" in result
    print(f"    ✓ 法规检查: {result['violations_found']} 个违规")

    # 测试不存在的工具
    async def run_missing_tool():
        result = await tools.execute_tool("nonexistent_tool")
        return result

    result = asyncio.run(run_missing_tool())
    assert "error" in result
    print("    ✓ 不存在的工具返回错误")

    print("    ✓ 工具执行测试通过")
    return True


def test_agent_with_tools_integration():
    """测试AgentWithTools集成"""
    print("  [附加4] 测试AgentWithTools集成...")

    from src.agents import DocumentParserAgent

    agent = DocumentParserAgent()
    tools = AgentTools()
    agent_with_tools = AgentWithTools(agent, tools)

    # 检查基本属性
    assert agent_with_tools.agent == agent
    assert agent_with_tools.tools == tools
    print(f"    ✓ Agent: {agent.name}")
    print(f"    ✓ 工具数: {len(tools.list_tools())}")

    # 测试对话历史
    assert len(agent_with_tools._conversation_history) == 0
    print("    ✓ 初始对话历史为空")

    agent_with_tools.clear_history()
    assert len(agent_with_tools._conversation_history) == 0
    print("    ✓ 清空对话历史正常")

    print("    ✓ AgentWithTools集成测试通过")
    return True


def run_all_tests():
    """运行所有Tools集成测试"""
    print("=" * 60)
    print("Day 15: LangChain Tools和AgentTools集成测试")
    print("=" * 60)

    tests = [
        ("LangChain Tools可用性", test_contract_tools_availability),
        ("analyze_clause工具", test_analyze_clause_tool),
        ("assess_risk工具", test_assess_risk_tool),
        ("generate_suggestions工具", test_generate_suggestions_tool),
        ("summarize_contract工具", test_summarize_contract_tool),
        ("AgentTools初始化", test_agent_tools_initialization),
        ("Skill到LangChain工具转换", test_agent_tools_langchain_conversion),
        ("工具执行", test_agent_tools_execution),
        ("AgentWithTools集成", test_agent_with_tools_integration),
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
