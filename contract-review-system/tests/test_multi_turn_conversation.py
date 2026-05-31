"""
多轮对话测试 - Day 23
测试多轮对话的历史存储、上下文注入、追问场景和上下文连贯性
"""
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ==================== 辅助函数 ====================

def run_test(test_name, test_func):
    """运行单个测试"""
    try:
        result = test_func()
        if asyncio.iscoroutine(result):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(result)
            finally:
                loop.close()
        print(f"  ✅ {test_name}")
        return True
    except Exception as e:
        print(f"  ❌ {test_name}: {e}")
        return False


def run_async(coro):
    """运行异步函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ==================== 模块导入测试 ====================

def test_multi_turn_handler_import():
    """测试多轮对话处理器导入"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    assert MultiTurnHandler is not None


def test_agents_module_export():
    """测试Agent模块导出MultiTurnHandler"""
    from src.agents import MultiTurnHandler
    assert MultiTurnHandler is not None


# ==================== 初始化测试 ====================

def test_handler_creation():
    """测试处理器创建"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    assert handler.intent_recognizer is not None
    assert handler.conversation_manager is not None


def test_handler_custom_init():
    """测试自定义初始化"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    from src.agents.intent_recognizer import IntentRecognizer
    from src.agents.conversation_context import ConversationManager
    
    recognizer = IntentRecognizer(mode="keyword")
    manager = ConversationManager(max_sessions=10)
    handler = MultiTurnHandler(
        intent_recognizer=recognizer,
        conversation_manager=manager,
    )
    assert handler.intent_recognizer is recognizer
    assert handler.conversation_manager is manager


def test_agent_callback_registration():
    """测试Agent回调注册"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    
    async def mock_callback(ctx):
        return {"status": "ok"}
    
    handler.register_agent_callback("test_agent", mock_callback)
    assert "test_agent" in handler._agent_callbacks


# ==================== 单轮对话测试 ====================

def test_single_turn_greeting():
    """测试单轮问候对话"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    result = run_async(handler.handle_message("s1", "你好"))
    
    assert result["session_id"] == "s1"
    assert result["intent"]["type"] == "greeting"
    assert result["agent"] == "system"
    assert result["response"] is not None
    assert len(result["response"]) > 0


def test_single_turn_with_contract():
    """测试单轮带合同的对话"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同，甲方为ABC公司，乙方为XYZ公司。合同金额10万元。"
    
    result = run_async(handler.handle_message(
        "s2", "帮我审查这份合同", contract_text=contract
    ))
    
    assert result["session_id"] == "s2"
    assert result["intent"]["type"] == "contract_review"
    assert result["agent"] == "coordinator"
    assert result["response"] is not None


def test_single_turn_risk_assessment():
    """测试单轮风险评估"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同，合同金额10万元，违约金比例30%。"
    
    result = run_async(handler.handle_message(
        "s3", "评估一下风险", contract_text=contract
    ))
    
    assert result["intent"]["type"] == "risk_assessment"
    assert result["agent"] == "risk_assessor"
    assert "风险" in result["response"]


def test_single_turn_no_contract_warning():
    """测试无合同文本时的提示"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    result = run_async(handler.handle_message("s4", "帮我审查这份合同"))
    
    # 应该提示需要合同文本
    assert result.get("needs_contract") is True
    assert "上传" in result["response"] or "提供" in result["response"]


# ==================== 多轮对话测试 ====================

def test_multi_turn_history():
    """测试多轮对话历史"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    
    # 第1轮：问候
    r1 = run_async(handler.handle_message("s5", "你好"))
    assert r1["intent"]["type"] == "greeting"
    
    # 第2轮：上传合同
    contract = "技术服务合同，甲方ABC公司。"
    r2 = run_async(handler.handle_message(
        "s5", "帮我审查合同", contract_text=contract
    ))
    assert r2["intent"]["type"] == "contract_review"
    
    # 第3轮：评估风险
    r3 = run_async(handler.handle_message("s5", "评估风险"))
    assert r3["intent"]["type"] == "risk_assessment"
    
    # 检查历史
    history = handler.get_session_history("s5")
    assert len(history) == 6  # 3轮 × 2条消息


def test_multi_turn_intent_chain():
    """测试多轮对话意图链"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同。"
    
    run_async(handler.handle_message("s6", "你好"))
    run_async(handler.handle_message("s6", "审查合同", contract_text=contract))
    run_async(handler.handle_message("s6", "评估风险"))
    run_async(handler.handle_message("s6", "检查合规"))
    
    context = handler.get_session_context("s6")
    assert context is not None
    chain = context["intent_chain"]
    assert "greeting" in chain
    assert "contract_review" in chain
    assert "risk_assessment" in chain
    assert "compliance_check" in chain


def test_multi_turn_agent_results_accumulate():
    """测试多轮对话Agent结果累积"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同，合同金额10万元。"
    
    # 第1轮：解析合同
    run_async(handler.handle_message(
        "s7", "审查合同", contract_text=contract
    ))
    
    # 第2轮：评估风险
    run_async(handler.handle_message("s7", "评估风险"))
    
    # 第3轮：检查合规
    run_async(handler.handle_message("s7", "检查合规"))
    
    context = handler.get_session_context("s7")
    assert len(context["agent_results"]) >= 2  # 至少2个Agent有结果


# ==================== 追问场景测试 ====================

async def test_follow_up_risk_after_parse():
    """测试追问场景：解析后评估风险"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同，违约金比例30%。"
    
    # 第1轮：审查合同（模拟document_parser结果）
    r1 = await handler.handle_message("s8", "审查合同", contract_text=contract)
    
    # 第2轮：追问风险
    r2 = await handler.handle_message("s8", "有什么风险")
    
    # 应该注入解析结果到风险评估上下文
    assert r2["intent"]["type"] == "risk_assessment"
    task_context = r2.get("context_summary", {})
    assert task_context.get("has_contract") is True


async def test_follow_up_report_after_analysis():
    """测试追问场景：分析后生成报告"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同。"
    
    # 第1轮：审查
    await handler.handle_message("s9", "审查合同", contract_text=contract)
    
    # 第2轮：风险评估
    await handler.handle_message("s9", "评估风险")
    
    # 第3轮：生成报告
    r3 = await handler.handle_message("s9", "生成报告")
    
    assert r3["intent"]["type"] == "report_generation"
    # 上下文应该包含之前的结果
    summary = r3.get("context_summary", {})
    assert len(summary.get("completed_agents", [])) >= 1


# ==================== 自定义回调测试 ====================

async def test_custom_agent_callback():
    """测试自定义Agent回调"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    
    async def custom_risk_callback(ctx):
        return {
            "status": "completed",
            "agent": "risk_assessor",
            "custom": True,
            "risk_level": "low",
            "risks": [{"level": "low", "description": "自定义风险评估结果"}],
        }
    
    handler.register_agent_callback("risk_assessor", custom_risk_callback)
    contract = "技术服务合同。"
    
    r = await handler.handle_message("s10", "评估风险", contract_text=contract)
    assert r["result"]["custom"] is True
    assert r["result"]["risk_level"] == "low"


async def test_callback_error_handling():
    """测试回调异常处理"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    
    async def failing_callback(ctx):
        raise ValueError("模拟Agent执行失败")
    
    handler.register_agent_callback("risk_assessor", failing_callback)
    contract = "技术服务合同。"
    
    r = await handler.handle_message("s11", "评估风险", contract_text=contract)
    assert r["result"]["status"] == "error"
    assert "失败" in r["result"]["error"]


# ==================== 回复格式测试 ====================

def test_response_format_greeting():
    """测试问候回复格式"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    r = run_async(handler.handle_message("s12", "你好"))
    assert "助手" in r["response"] or "帮助" in r["response"] or "您好" in r["response"]


def test_response_format_risk():
    """测试风险评估回复格式"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同，违约金比例30%。"
    r = run_async(handler.handle_message("s13", "评估风险", contract_text=contract))
    
    response = r["response"]
    assert "风险" in response
    assert "level" in r["result"] or "risk_level" in r["result"]


def test_response_format_report():
    """测试报告生成回复格式"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同。"
    r = run_async(handler.handle_message("s14", "生成报告", contract_text=contract))
    
    assert "报告" in r["response"]


# ==================== 会话管理测试 ====================

def test_session_context_summary():
    """测试会话上下文摘要"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同。"
    
    run_async(handler.handle_message("s15", "审查合同", contract_text=contract))
    run_async(handler.handle_message("s15", "评估风险"))
    
    summary = handler.get_session_context("s15")
    assert summary is not None
    assert summary["session_id"] == "s15"
    assert summary["message_count"] == 4  # 2轮 × 2条消息
    assert summary["has_contract"] is True
    assert len(summary["intent_chain"]) == 2


def test_session_clear():
    """测试清空会话"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    run_async(handler.handle_message("s16", "你好"))
    
    # 清空前有历史
    history = handler.get_session_history("s16")
    assert len(history) > 0
    
    # 清空
    handler.clear_session("s16")
    
    # 清空后无历史
    history = handler.get_session_history("s16")
    assert len(history) == 0


def test_multiple_sessions():
    """测试多会话隔离"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    
    run_async(handler.handle_message("session-a", "你好"))
    run_async(handler.handle_message("session-b", "审查合同", contract_text="合同A"))
    
    history_a = handler.get_session_history("session-a")
    history_b = handler.get_session_history("session-b")
    
    assert len(history_a) == 2  # 1轮
    assert len(history_b) == 2  # 1轮
    
    # 会话独立
    context_a = handler.get_session_context("session-a")
    context_b = handler.get_session_context("session-b")
    assert context_a["intent_chain"] == ["greeting"]
    assert context_b["intent_chain"] == ["contract_review"]


# ==================== 路由信息测试 ====================

def test_supported_intents():
    """测试获取支持的意图列表"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    intents = handler.get_supported_intents()
    
    assert isinstance(intents, list)
    assert len(intents) == 8
    
    types = [i["intent"] for i in intents]
    assert "contract_review" in types
    assert "risk_assessment" in types
    assert "greeting" in types


def test_intent_routing():
    """测试意图路由映射"""
    from src.agents.multi_turn_handler import INTENT_AGENT_ROUTING
    from src.agents.intent_recognizer import IntentType
    
    # 每个意图都有对应的Agent
    for intent_type in IntentType:
        assert intent_type in INTENT_AGENT_ROUTING
        routing = INTENT_AGENT_ROUTING[intent_type]
        assert "agent" in routing
        assert "description" in routing
        assert "requires_contract" in routing


# ==================== 文件信息测试 ====================

def test_file_info_passed():
    """测试文件信息传递"""
    from src.agents.multi_turn_handler import MultiTurnHandler
    
    handler = MultiTurnHandler()
    contract = "技术服务合同内容。"
    file_info = {"filename": "test_contract.pdf", "type": "pdf"}
    
    r = run_async(handler.handle_message(
        "s17", "审查合同", contract_text=contract, file_info=file_info
    ))
    
    # 合同文本应该被存储
    ctx = handler.conversation_manager.get_or_create("s17")
    assert ctx.get_contract_text() == contract


# ==================== 测试运行器 ====================

def run_all_tests():
    """运行所有多轮对话测试"""
    print("\n" + "=" * 60)
    print("📋 Day 23: 多轮对话测试")
    print("=" * 60)
    
    tests = [
        # 模块导入测试
        ("多轮处理器导入", test_multi_turn_handler_import),
        ("Agent模块导出", test_agents_module_export),
        
        # 初始化测试
        ("处理器创建", test_handler_creation),
        ("自定义初始化", test_handler_custom_init),
        ("Agent回调注册", test_agent_callback_registration),
        
        # 单轮对话测试
        ("单轮问候", test_single_turn_greeting),
        ("单轮带合同", test_single_turn_with_contract),
        ("单轮风险评估", test_single_turn_risk_assessment),
        ("无合同提示", test_single_turn_no_contract_warning),
        
        # 多轮对话测试
        ("多轮历史", test_multi_turn_history),
        ("多轮意图链", test_multi_turn_intent_chain),
        ("多轮结果累积", test_multi_turn_agent_results_accumulate),
        
        # 追问场景测试
        ("追问-风险评估", lambda: test_follow_up_risk_after_parse()),
        ("追问-生成报告", lambda: test_follow_up_report_after_analysis()),
        
        # 自定义回调测试
        ("自定义回调", lambda: test_custom_agent_callback()),
        ("回调异常处理", lambda: test_callback_error_handling()),
        
        # 回复格式测试
        ("回复-问候", test_response_format_greeting),
        ("回复-风险评估", test_response_format_risk),
        ("回复-报告生成", test_response_format_report),
        
        # 会话管理测试
        ("会话摘要", test_session_context_summary),
        ("清空会话", test_session_clear),
        ("多会话隔离", test_multiple_sessions),
        
        # 路由信息测试
        ("支持的意图", test_supported_intents),
        ("意图路由映射", test_intent_routing),
        
        # 文件信息测试
        ("文件信息传递", test_file_info_passed),
    ]
    
    passed = 0
    failed = 0
    failed_tests = []
    
    for test_name, test_func in tests:
        if run_test(test_name, test_func):
            passed += 1
        else:
            failed += 1
            failed_tests.append(test_name)
    
    print("\n" + "-" * 60)
    print(f"📊 测试结果: {passed}/{passed + failed} 通过")
    
    if failed > 0:
        print(f"\n❌ 失败的测试:")
        for t in failed_tests:
            print(f"  - {t}")
    else:
        print("🎉 全部通过！")
    
    print("=" * 60)
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all_tests()
    sys.exit(0 if failed == 0 else 1)
