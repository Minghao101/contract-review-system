"""
记忆系统测试模块
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.memory.memory_layer import MemoryLayer
from src.memory.private_memory import AgentPrivateMemory
from src.memory.shared_memory import SharedMemoryManager


def test_memory_layer():
    """测试记忆层次"""
    print("测试MemoryLayer...")

    assert MemoryLayer.CONTEXT.value == "context"
    assert MemoryLayer.ANALYSIS.value == "analysis"
    assert MemoryLayer.DECISION.value == "decision"

    print("MemoryLayer测试通过！")
    return True


def test_private_memory():
    """测试私有记忆"""
    print("测试AgentPrivateMemory...")

    memory = AgentPrivateMemory(agent_id="test_agent")

    # 测试上下文管理
    memory.update_context("user", "你好")
    memory.update_context("assistant", "你好！有什么可以帮助你的？")

    context = memory.get_context()
    assert len(context) == 2
    assert context[0]["content"] == "你好"

    # 测试最近N条
    recent = memory.get_context(last_n=1)
    assert len(recent) == 1

    # 测试任务状态
    memory.set_task_state("task_001", {"status": "running"})
    state = memory.get_task_state("task_001")
    assert state["status"] == "running"

    # 测试缓存
    memory.set_cache("key1", "value1", ttl_seconds=60)
    assert memory.get_cache("key1") == "value1"

    # 测试状态
    status = memory.get_status()
    assert status["agent_id"] == "test_agent"
    assert status["context_length"] == 2

    print("AgentPrivateMemory测试通过！")
    return True


def test_context_compression():
    """测试上下文压缩"""
    print("测试上下文压缩...")

    memory = AgentPrivateMemory(agent_id="test_agent", max_context_length=10)

    # 添加7条上下文（70%）
    for i in range(7):
        memory.update_context("user", f"问题{i}")

    # 此时不压缩（70% < 80%）
    summary = memory.compress_context()
    assert summary == ""

    # 添加更多内容超过80%
    for i in range(4):
        memory.update_context("assistant", f"回答{i}")

    # 压缩后应该有摘要
    summary = memory.compress_context()
    assert summary != ""

    # 获取完整上下文
    full_context = memory.get_full_context()
    assert "compressed_summary" in full_context
    assert "recent_context" in full_context

    print("上下文压缩测试通过！")
    return True


def test_private_memory_persistence():
    """测试私有记忆持久化"""
    print("测试私有记忆持久化...")

    memory = AgentPrivateMemory(agent_id="test_agent")
    memory.update_context("user", "测试问题")
    memory.update_context("assistant", "测试回答")
    memory.set_task_state("task_001", {"status": "done"})
    memory.set_cache("key1", "value1")

    # 保存到文件
    test_file = "test_memory.json"
    memory.save_to_file(test_file)

    # 创建新实例并加载
    memory2 = AgentPrivateMemory(agent_id="test_agent_2")
    success = memory2.load_from_file(test_file)

    assert success == True
    assert memory2.get_context()[-1]["content"] == "测试回答"
    assert memory2.get_task_state("task_001")["status"] == "done"

    # 清理测试文件
    os.remove(test_file)

    print("私有记忆持久化测试通过！")
    return True


def test_shared_memory():
    """测试共享记忆"""
    print("测试SharedMemoryManager...")

    manager = SharedMemoryManager(contract_id="contract_001")

    # 测试写入
    version = manager.write(
        agent_id="parser",
        key="document_structure",
        value={"clauses": ["条款1", "条款2"]},
        layer=MemoryLayer.CONTEXT
    )
    assert version == 1

    # 测试读取
    value = manager.read(
        agent_id="analyzer",
        key="document_structure",
        layer=MemoryLayer.CONTEXT
    )
    assert value["clauses"] == ["条款1", "条款2"]

    # 测试版本控制
    version2 = manager.write(
        agent_id="parser",
        key="document_structure",
        value={"clauses": ["条款1", "条款2", "条款3"]},
        layer=MemoryLayer.CONTEXT
    )
    assert version2 == 2

    # 测试查询
    results = manager.query(
        agent_id="test",
        layer=MemoryLayer.CONTEXT,
        prefix="document"
    )
    assert "document_structure" in results

    # 测试删除
    success = manager.delete(
        agent_id="test",
        key="document_structure",
        layer=MemoryLayer.CONTEXT
    )
    assert success == True

    # 测试删除不存在的键
    success = manager.delete(
        agent_id="test",
        key="nonexistent",
        layer=MemoryLayer.CONTEXT
    )
    assert success == False

    print("SharedMemoryManager测试通过！")
    return True


def test_shared_memory_subscribe():
    """测试共享记忆订阅"""
    print("测试SharedMemory订阅...")

    manager = SharedMemoryManager(contract_id="contract_002")
    notifications = []

    # 定义回调函数
    def on_change(key, agent_id, value):
        notifications.append({
            "key": key,
            "agent_id": agent_id,
            "value": value
        })

    # 订阅
    manager.subscribe("test_key", on_change)

    # 写入触发通知
    manager.write(
        agent_id="agent_001",
        key="test_key",
        value="test_value",
        layer=MemoryLayer.ANALYSIS
    )

    assert len(notifications) == 1
    assert notifications[0]["key"] == "test_key"
    assert notifications[0]["agent_id"] == "agent_001"

    # 取消订阅
    manager.unsubscribe("test_key", on_change)

    # 再次写入，不应触发通知
    manager.write(
        agent_id="agent_002",
        key="test_key",
        value="test_value_2",
        layer=MemoryLayer.ANALYSIS
    )

    assert len(notifications) == 1  # 仍然是1

    print("SharedMemory订阅测试通过！")
    return True


def test_multi_agent_collaboration():
    """测试多Agent协作场景"""
    print("测试多Agent协作场景...")

    manager = SharedMemoryManager(contract_id="contract_003")

    # 模拟：合同解析Agent写入
    manager.write(
        agent_id="parser",
        key="metadata",
        value={"title": "劳动合同", "parties": ["甲方", "乙方"]},
        layer=MemoryLayer.CONTEXT
    )

    # 模拟：条款分析Agent读取并写入分析结果
    metadata = manager.read("analyzer", "metadata", MemoryLayer.CONTEXT)
    assert metadata["title"] == "劳动合同"

    manager.write(
        agent_id="analyzer",
        key="clause_analysis",
        value={"clause_1": {"risk": "low"}, "clause_2": {"risk": "high"}},
        layer=MemoryLayer.ANALYSIS
    )

    # 模拟：风险评估Agent读取
    analysis = manager.read("risk_assessor", "clause_analysis", MemoryLayer.ANALYSIS)
    assert analysis["clause_2"]["risk"] == "high"

    # 获取统计
    stats = manager.get_stats()
    assert stats["context_count"] == 1
    assert stats["analysis_count"] == 1

    print("多Agent协作场景测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行记忆系统测试")
    print("=" * 50)

    tests = [
        test_memory_layer(),
        test_private_memory(),
        test_context_compression(),
        test_private_memory_persistence(),
        test_shared_memory(),
        test_shared_memory_subscribe(),
        test_multi_agent_collaboration(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
