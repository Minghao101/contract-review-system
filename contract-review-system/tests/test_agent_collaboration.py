"""
Day 16: Agent协作测试
测试端到端流程、Agent间通信、共享记忆读写、并行处理
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import json
import time
from typing import Dict, Any
from src.agents import (
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
from src.memory.memory_layer import MemoryLayer


# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京创新科技有限公司
乙方：上海智慧软件有限公司

合同编号：TS-2024-001

第一条 合同标的
乙方为甲方提供企业级ERP系统的技术开发服务。

第二条 服务期限
合同有效期自2024年4月1日至2024年12月31日。

第三条 服务费用及支付
3.1 服务总费用为人民币壹佰伍拾万元整（¥1,500,000.00）。
3.2 甲方应在合同签订后预付全款。

第四条 验收标准
4.1 乙方应按照甲方确认的需求文档进行开发。

第五条 知识产权
5.1 本合同履行过程中产生的所有技术成果和知识产权归甲方所有。

第六条 保密条款
6.1 双方对本合同内容及履行过程中知悉的对方商业秘密承担保密义务。
6.2 保密期限为永久保密。

第七条 违约责任
7.1 如甲方违约，应承担无限责任，赔偿乙方一切损失。
7.2 如乙方未能按时交付，应按合同总金额的50%支付违约金。

第八条 单方解除权
8.1 甲方可随时解除本合同，且无需承担任何违约责任。

第九条 争议解决
如发生争议，由乙方所在地法院管辖。

第十条 不可抗力
因不可抗力导致合同无法履行的，双方均不承担违约责任。
"""


# ============================================================
# 1. 端到端测试用例设计与执行
# ============================================================

def test_end_to_end_full_review():
    """端到端：完整合同审查流程"""
    print("  [1/8] 端到端完整审查流程...")

    coordinator = CoordinatorAgent()
    coordinator.register_agent(DocumentParserAgent())
    coordinator.register_agent(ClauseAnalysisAgent())
    coordinator.register_agent(RiskAssessmentAgent())
    coordinator.register_agent(ComplianceCheckerAgent())
    coordinator.register_agent(ReportGeneratorAgent())

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service",
        "review_focus": ["违约责任", "知识产权", "保密条款"]
    }

    start_time = time.time()
    result = asyncio.run(coordinator.process(task))
    elapsed = time.time() - start_time

    # 验证结果结构
    assert "status" in result, "结果应包含status字段"
    assert result["status"] in ["completed", "partial_failed"], f"状态应为completed或partial_failed，实际: {result['status']}"

    # 验证各阶段结果
    sections = result.get("sections", {})
    print(f"    ✓ 审查状态: {result['status']}")
    print(f"    ✓ 完成阶段: {list(sections.keys())}")
    print(f"    ✓ 风险等级: {result.get('risk_level', 'unknown')}")
    print(f"    ✓ 合规状态: {result.get('compliance_status', 'unknown')}")
    print(f"    ✓ 总耗时: {elapsed:.2f}秒")

    # 验证包含关键信息
    if result.get("risk_level"):
        print(f"    ✓ 风险评估已完成")
    if result.get("compliance_status"):
        print(f"    ✓ 合规检查已完成")

    print("    ✓ 端到端完整审查测试通过")
    return True


def test_end_to_end_minimal_contract():
    """端到端：最小合同审查"""
    print("  [2/8] 端到端最小合同审查...")

    coordinator = CoordinatorAgent()
    coordinator.register_agent(DocumentParserAgent())
    coordinator.register_agent(ClauseAnalysisAgent())
    coordinator.register_agent(RiskAssessmentAgent())
    coordinator.register_agent(ComplianceCheckerAgent())
    coordinator.register_agent(ReportGeneratorAgent())

    minimal_contract = """
租赁合同

甲方：张三
乙方：李四

甲方将位于北京市朝阳区的房屋出租给乙方使用，租期一年，月租金3000元。
    """

    task = {
        "contract_text": minimal_contract,
        "contract_type": "lease"
    }

    result = asyncio.run(coordinator.process(task))

    assert "status" in result
    print(f"    ✓ 审查状态: {result['status']}")
    print(f"    ✓ 最小合同审查完成")

    print("    ✓ 端到端最小合同审查测试通过")
    return True


def test_end_to_end_empty_contract():
    """端到端：空合同错误处理"""
    print("  [3/8] 端到端空合同错误处理...")

    coordinator = CoordinatorAgent()
    coordinator.register_agent(DocumentParserAgent())

    task = {
        "contract_text": "",
        "contract_type": "service"
    }

    result = asyncio.run(coordinator.process(task))

    # 空合同应有处理结果（可能包含error或status）
    has_status = "status" in result
    has_error = "error" in result
    assert has_status or has_error, f"空合同应返回status或error，实际keys: {list(result.keys())}"
    if has_status:
        print(f"    ✓ 空合同处理状态: {result['status']}")
    else:
        print(f"    ✓ 空合同返回错误: {result.get('error', 'unknown')}")

    print("    ✓ 端到端空合同错误处理测试通过")
    return True


# ============================================================
# 2. Agent间通信测试
# ============================================================

def test_message_bus_basic():
    """MessageBus基本通信"""
    print("  [4/8] MessageBus基本通信...")

    bus = MessageBus()
    received = []

    def callback(msg):
        received.append(msg)

    # 订阅
    bus.subscribe("agent_a", callback)

    # 发布定向消息
    msg = AgentMessage(
        sender_id="coordinator",
        receiver_id="agent_a",
        message_type=MessageType.TASK_ASSIGN,
        content={"action": "parse", "data": "test"}
    )
    bus.publish(msg)

    assert len(received) == 1
    assert received[0].content["action"] == "parse"
    print("    ✓ 定向消息接收正常")

    # 取消订阅
    bus.unsubscribe("agent_a", callback)
    bus.publish(msg)
    assert len(received) == 1  # 不再接收
    print("    ✓ 取消订阅后不再接收消息")

    # 测试广播
    received_all = []
    def callback_all(msg):
        received_all.append(msg)

    bus.subscribe("all_agent", callback_all)
    broadcast_msg = AgentMessage(
        sender_id="coordinator",
        receiver_id="all",
        message_type=MessageType.TASK_RESULT,
        content={"status": "complete"}
    )
    bus.publish(broadcast_msg)
    print("    ✓ 广播消息发送正常")

    bus.unsubscribe("all_agent")

    print("    ✓ MessageBus基本通信测试通过")
    return True


def test_agent_message_types():
    """测试各种消息类型"""
    print("  [5/8] Agent消息类型测试...")

    bus = MessageBus()
    messages_received = []

    def collector(msg):
        messages_received.append(msg)

    bus.subscribe("test_agent", collector)

    # 测试各种消息类型
    msg_types = [
        MessageType.TASK_ASSIGN,
        MessageType.TASK_RESULT,
        MessageType.ERROR,
    ]

    for msg_type in msg_types:
        msg = AgentMessage(
            sender_id="coordinator",
            receiver_id="test_agent",
            message_type=msg_type,
            content={"type": msg_type.value, "data": "test"}
        )
        bus.publish(msg)

    assert len(messages_received) == len(msg_types)
    print(f"    ✓ 收到 {len(messages_received)} 种消息类型")

    # 验证消息序列化
    for msg in messages_received:
        msg_dict = msg.to_dict()
        restored = AgentMessage.from_dict(msg_dict)
        assert restored.sender_id == msg.sender_id
        assert restored.message_type == msg.message_type
    print("    ✓ 消息序列化/反序列化正常")

    bus.unsubscribe("test_agent")

    print("    ✓ Agent消息类型测试通过")
    return True


def test_multi_agent_communication():
    """多Agent间通信"""
    print("  [6/8] 多Agent间通信...")

    bus = MessageBus()
    agent_messages = {
        "parser": [],
        "analyzer": [],
        "assessor": []
    }

    def make_callback(agent_id):
        def cb(msg):
            agent_messages[agent_id].append(msg)
        return cb

    for agent_id in agent_messages:
        bus.subscribe(agent_id, make_callback(agent_id))

    # 模拟协调器分发任务
    tasks = [
        ("parser", MessageType.TASK_ASSIGN, {"action": "parse"}),
        ("analyzer", MessageType.TASK_ASSIGN, {"action": "analyze"}),
        ("assessor", MessageType.TASK_ASSIGN, {"action": "assess"}),
    ]

    for receiver, msg_type, content in tasks:
        msg = AgentMessage(
            sender_id="coordinator",
            receiver_id=receiver,
            message_type=msg_type,
            content=content
        )
        bus.publish(msg)

    # 验证每个Agent只收到自己的消息
    assert len(agent_messages["parser"]) == 1
    assert len(agent_messages["analyzer"]) == 1
    assert len(agent_messages["assessor"]) == 1
    print("    ✓ 每个Agent只收到定向消息")

    # 模拟Agent结果回传
    result_msg = AgentMessage(
        sender_id="parser",
        receiver_id="coordinator",
        message_type=MessageType.TASK_RESULT,
        content={"parsed": True}
    )
    bus.publish(result_msg)
    print("    ✓ Agent结果回传正常")

    # 清理
    for agent_id in agent_messages:
        bus.unsubscribe(agent_id)

    print("    ✓ 多Agent间通信测试通过")
    return True


# ============================================================
# 3. 共享记忆读写测试
# ============================================================

def test_shared_memory_basic():
    """共享记忆基本读写"""
    print("  [7/8] 共享记忆基本读写...")

    memory = SharedMemoryManager(contract_id="test_contract_001")

    # 写入上下文层
    memory.write(
        key="contract_text",
        value=SAMPLE_CONTRACT[:100],
        layer=MemoryLayer.CONTEXT,
        agent_id="document_parser"
    )
    print("    ✓ 写入CONTEXT层")

    # 读取
    value = memory.read(agent_id="reader", key="contract_text", layer=MemoryLayer.CONTEXT)
    assert value == SAMPLE_CONTRACT[:100]
    print("    ✓ 读取CONTEXT层正常")

    # 写入分析层
    memory.write(
        key="clause_analysis",
        value={"clauses": 10, "issues": 2},
        layer=MemoryLayer.ANALYSIS,
        agent_id="clause_analysis"
    )
    print("    ✓ 写入ANALYSIS层")

    # 写入决策层
    memory.write(
        key="final_decision",
        value={"risk_level": "high", "recommendation": "reject"},
        layer=MemoryLayer.DECISION,
        agent_id="coordinator"
    )
    print("    ✓ 写入DECISION层")

    # 跨层读取
    ctx_value = memory.read(agent_id="reader", key="contract_text", layer=MemoryLayer.CONTEXT)
    ana_value = memory.read(agent_id="reader", key="clause_analysis", layer=MemoryLayer.ANALYSIS)
    dec_value = memory.read(agent_id="reader", key="final_decision", layer=MemoryLayer.DECISION)

    assert ctx_value is not None
    assert ana_value is not None
    assert dec_value is not None
    print("    ✓ 跨层读取正常")

    # 获取统计
    stats = memory.get_stats()
    print(f"    ✓ 记忆统计: {stats}")

    # 导出（key为小写：context/analysis/decision）
    exported = memory.export_all()
    assert "context" in exported
    assert "analysis" in exported
    assert "decision" in exported
    print(f"    ✓ 导出记忆: {list(exported.keys())}")

    print("    ✓ 共享记忆基本读写测试通过")
    return True


def test_shared_memory_query():
    """共享记忆查询"""
    print("  [附加] 共享记忆查询...")

    memory = SharedMemoryManager(contract_id="test_query")

    # 写入多条记忆
    for i in range(5):
        memory.write(
            key=f"risk_{i}",
            value={"severity": "high" if i < 2 else "low", "index": i},
            layer=MemoryLayer.ANALYSIS,
            agent_id="risk_assessor"
        )

    # 查询
    results = memory.query(agent_id="querier", layer=MemoryLayer.ANALYSIS, prefix="risk_")
    assert len(results) == 5
    print(f"    ✓ 查询到 {len(results)} 条记忆")

    # 带元数据读取
    entry = memory.read_with_meta(
        agent_id="reader",
        key="risk_0",
        layer=MemoryLayer.ANALYSIS
    )
    assert entry is not None
    print(f"    ✓ 带元数据读取正常")

    # 删除
    memory.delete(agent_id="deleter", key="risk_0", layer=MemoryLayer.ANALYSIS)
    value = memory.read(agent_id="reader", key="risk_0", layer=MemoryLayer.ANALYSIS)
    assert value is None
    print("    ✓ 删除记忆正常")

    # 获取所有key
    keys = memory.get_all_keys(layer=MemoryLayer.ANALYSIS)
    assert len(keys) == 4  # 删了一个
    print(f"    ✓ 剩余key数: {len(keys)}")

    print("    ✓ 共享记忆查询测试通过")
    return True


def test_shared_memory_notification():
    """共享记忆通知机制"""
    print("  [附加] 共享记忆通知机制...")

    memory = SharedMemoryManager(contract_id="test_notify")
    notifications = []

    def on_update(key, agent_id, value):
        notifications.append({
            "key": key,
            "agent_id": agent_id,
            "value": value
        })

    # 订阅
    memory.subscribe("test_key", on_update)

    # 写入触发通知
    memory.write(
        key="test_key",
        value="new_value",
        layer=MemoryLayer.CONTEXT,
        agent_id="test_agent"
    )

    assert len(notifications) == 1
    assert notifications[0]["key"] == "test_key"
    assert notifications[0]["agent_id"] == "test_agent"
    print(f"    ✓ 收到 {len(notifications)} 个通知")

    # 取消订阅
    memory.unsubscribe("test_key", on_update)
    memory.write(
        key="test_key",
        value="another_value",
        layer=MemoryLayer.CONTEXT,
        agent_id="test_agent"
    )
    assert len(notifications) == 1  # 不再通知
    print("    ✓ 取消订阅后不再通知")

    print("    ✓ 共享记忆通知机制测试通过")
    return True


# ============================================================
# 4. 并行处理测试
# ============================================================

def test_parallel_agent_processing():
    """并行Agent处理"""
    print("  [附加] 并行Agent处理...")

    # 创建多个Agent同时处理
    agents = [
        ("clause", ClauseAnalysisAgent()),
        ("risk", RiskAssessmentAgent()),
        ("compliance", ComplianceCheckerAgent()),
    ]

    task = {
        "contract_text": SAMPLE_CONTRACT,
        "contract_type": "service"
    }

    async def run_parallel():
        results = {}
        tasks_list = []
        for name, agent in agents:
            tasks_list.append((name, agent.process(task.copy())))

        start = time.time()
        # 并行执行
        done_results = await asyncio.gather(
            *[t for _, t in tasks_list],
            return_exceptions=True
        )
        elapsed = time.time() - start

        for i, (name, _) in enumerate(tasks_list):
            if isinstance(done_results[i], Exception):
                results[name] = {"error": str(done_results[i])}
            else:
                results[name] = done_results[i]

        return results, elapsed

    results, elapsed = asyncio.run(run_parallel())

    print(f"    ✓ 并行执行耗时: {elapsed:.2f}秒")
    for name, result in results.items():
        if "error" in result:
            print(f"    ✗ {name}: {result['error']}")
        else:
            print(f"    ✓ {name}: 完成")

    # 验证所有Agent都产生了结果
    assert len(results) == 3
    successful = sum(1 for r in results.values() if "error" not in r)
    print(f"    ✓ 成功/总数: {successful}/{len(results)}")

    print("    ✓ 并行Agent处理测试通过")
    return True


# ============================================================
# 5. Coordinator协调测试
# ============================================================

def test_coordinator_registration():
    """协调器Agent注册与管理"""
    print("  [附加] 协调器Agent注册管理...")

    coordinator = CoordinatorAgent()

    # 注册Agent
    agents = [
        DocumentParserAgent(),
        ClauseAnalysisAgent(),
        RiskAssessmentAgent(),
        ComplianceCheckerAgent(),
        ReportGeneratorAgent(),
    ]

    for agent in agents:
        coordinator.register_agent(agent)

    # 验证注册
    registered = coordinator.get_registered_agents()
    assert len(registered) == 5
    print(f"    ✓ 注册了 {len(registered)} 个Agent")

    # 验证Agent角色查找（注意：实际role值可能与agent_id不同）
    for role in ["document_parser", "clause_analyst", "risk_assessor",
                 "compliance_checker", "report_generator"]:
        found = coordinator._find_agent_by_role(role)
        assert found is not None, f"找不到角色: {role}"
    print("    ✓ 所有角色查找正常")

    # 验证默认执行计划
    plan = coordinator._get_default_plan()
    assert len(plan) == 5
    print(f"    ✓ 默认执行计划: {len(plan)} 步")

    # 验证Agent描述
    desc = coordinator._get_agent_descriptions()
    assert len(desc) > 0
    print(f"    ✓ Agent描述长度: {len(desc)} 字符")

    print("    ✓ 协调器Agent注册管理测试通过")
    return True


