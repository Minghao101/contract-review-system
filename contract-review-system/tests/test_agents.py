"""
Agent基础测试模块
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.agents.base_agent import BaseAgent
from src.agents.communication import AgentMessage, MessageType, MessageBus


class MockAgent(BaseAgent):
    """模拟Agent用于测试"""

    async def process(self, task: dict) -> dict:
        """处理任务"""
        return {
            "agent_id": self.agent_id,
            "status": "completed",
            "result": f"任务已处理: {task.get('content', '')}"
        }


def test_base_agent():
    """测试BaseAgent"""
    print("测试BaseAgent...")

    agent = MockAgent(
        agent_id="test_agent_001",
        name="测试Agent",
        role="测试",
        description="用于测试的Agent"
    )

    # 测试Agent状态
    assert agent.agent_id == "test_agent_001"
    assert agent.name == "测试Agent"
    assert agent.is_running == False

    # 测试状态获取
    status = agent.get_status()
    assert status["agent_id"] == "test_agent_001"
    assert status["is_running"] == False

    print("BaseAgent测试通过！")
    return True


async def test_agent_process():
    """测试Agent任务处理"""
    print("测试Agent任务处理...")

    agent = MockAgent(
        agent_id="test_agent_002",
        name="测试Agent2",
        role="测试"
    )

    # 测试任务处理
    task = {"content": "测试任务"}
    result = await agent.process(task)

    assert result["status"] == "completed"
    assert "测试任务" in result["result"]

    print("Agent任务处理测试通过！")
    return True


def test_message():
    """测试消息"""
    print("测试消息...")

    message = AgentMessage(
        sender_id="agent_001",
        receiver_id="agent_002",
        message_type=MessageType.TASK_ASSIGN,
        content={"task_id": "task_001", "content": "测试任务"}
    )

    # 测试消息属性
    assert message.sender_id == "agent_001"
    assert message.receiver_id == "agent_002"
    assert message.message_type == MessageType.TASK_ASSIGN

    # 测试序列化
    msg_dict = message.to_dict()
    assert msg_dict["sender_id"] == "agent_001"

    # 测试反序列化
    msg_restored = AgentMessage.from_dict(msg_dict)
    assert msg_restored.sender_id == "agent_001"

    print("消息测试通过！")
    return True


def test_message_bus():
    """测试消息总线"""
    print("测试消息总线...")

    bus = MessageBus()
    received_messages = []

    # 订阅消息
    def callback(message):
        received_messages.append(message)

    bus.subscribe("agent_002", callback)

    # 发布消息
    message = AgentMessage(
        sender_id="agent_001",
        receiver_id="agent_002",
        message_type=MessageType.NOTIFICATION,
        content={"info": "测试通知"}
    )
    bus.publish(message)

    # 验证消息接收
    assert len(received_messages) == 1
    assert received_messages[0].sender_id == "agent_001"

    print("消息总线测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行Agent基础测试")
    print("=" * 50)

    tests = [
        test_base_agent(),
        asyncio.run(test_agent_process()),
        test_message(),
        test_message_bus(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
