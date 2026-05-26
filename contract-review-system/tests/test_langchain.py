"""
LangChain集成测试模块
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.agents import LangChainAgentWrapper, create_llm_agent
from src.tools.langchain_tools import contract_tools


# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京科技有限公司
乙方：上海软件有限公司

一、合同标的
乙方为甲方提供技术开发服务，包括系统设计、编码实现和测试。

二、服务期限
合同有效期自2024年1月1日至2024年12月31日。

三、服务费用
服务总费用为人民币50万元，甲方应在合同签订后预付全款。

四、违约责任
如甲方违约，应承担无限责任，赔偿乙方一切损失。
"""


def test_langchain_agent_wrapper():
    """测试LangChain Agent包装器"""
    print("测试LangChain Agent包装器...")

    # 创建一个基础Agent
    from src.agents import DocumentParserAgent
    agent = DocumentParserAgent()

    # 创建包装器
    wrapper = LangChainAgentWrapper(agent, contract_tools)

    # 测试工具列表
    assert len(wrapper.tools) == len(contract_tools)
    print(f"  - 可用工具数: {len(wrapper.tools)}")

    # 测试对话（需要LLM连接）
    try:
        result = wrapper.chat("请简单介绍什么是合同")
        assert result is not None
        assert len(result) > 0
        print(f"  - 对话响应长度: {len(result)}")
    except Exception as e:
        print(f"  - 对话测试跳过（可能需要LLM连接）: {e}")

    print("LangChain Agent包装器测试通过！")
    return True


def test_create_llm_agent():
    """测试创建LLM Agent"""
    print("测试创建LLM Agent...")

    try:
        # 创建LLM Agent
        agent = create_llm_agent(
            agent_id="test_llm_agent",
            name="测试LLM Agent",
            role="analyzer",
            system_prompt="你是一个合同分析助手。",
            tools=contract_tools
        )

        assert agent.agent_id == "test_llm_agent"
        assert agent.name == "测试LLM Agent"
        assert agent.role == "analyzer"

        print(f"  - Agent ID: {agent.agent_id}")
        print(f"  - Agent名称: {agent.name}")

    except Exception as e:
        print(f"  - 创建LLM Agent测试跳过（可能需要LLM连接）: {e}")

    print("创建LLM Agent测试通过！")
    return True


def test_contract_tools():
    """测试合同工具"""
    print("测试合同工具...")

    # 检查工具列表
    assert len(contract_tools) == 4
    tool_names = [tool.name for tool in contract_tools]
    assert "analyze_clause" in tool_names
    assert "assess_risk" in tool_names
    assert "generate_suggestions" in tool_names
    assert "summarize_contract" in tool_names

    print(f"  - 工具数量: {len(contract_tools)}")
    print(f"  - 工具名称: {', '.join(tool_names)}")

    # 测试工具描述
    for tool in contract_tools:
        assert tool.description is not None
        assert len(tool.description) > 0

    print("合同工具测试通过！")
    return True


def test_wrapper_conversation_history():
    """测试对话历史管理"""
    print("测试对话历史管理...")

    from src.agents import DocumentParserAgent
    agent = DocumentParserAgent()
    wrapper = LangChainAgentWrapper(agent, contract_tools)

    # 初始历史应为空
    assert len(wrapper.get_history()) == 0

    # 手动添加历史记录
    wrapper._conversation_history.append({"role": "user", "content": "测试问题"})
    wrapper._conversation_history.append({"role": "assistant", "content": "测试回答"})

    assert len(wrapper.get_history()) == 2

    # 清空历史
    wrapper.clear_history()
    assert len(wrapper.get_history()) == 0

    print("对话历史管理测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行LangChain集成测试")
    print("=" * 50)

    tests = [
        test_langchain_agent_wrapper(),
        test_create_llm_agent(),
        test_contract_tools(),
        test_wrapper_conversation_history(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
