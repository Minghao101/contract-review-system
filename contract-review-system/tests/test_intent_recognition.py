"""
意图识别与Agent路由测试 - Day 22
测试意图识别、对话上下文管理和Agent路由
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ==================== 辅助函数 ====================

def run_test(test_name, test_func):
    """运行单个测试"""
    try:
        test_func()
        print(f"  ✅ {test_name}")
        return True
    except Exception as e:
        print(f"  ❌ {test_name}: {e}")
        return False


# ==================== 意图识别测试 ====================

def test_intent_recognizer_import():
    """测试意图识别器导入"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType, Intent
    assert IntentRecognizer is not None
    assert IntentType is not None
    assert Intent is not None


def test_intent_type_enum():
    """测试意图类型枚举"""
    from src.agents.intent_recognizer import IntentType
    
    expected_types = [
        "contract_review", "clause_analysis", "risk_assessment",
        "compliance_check", "report_generation", "question_answer",
        "greeting", "unknown"
    ]
    
    for t in expected_types:
        assert IntentType(t), f"意图类型不存在: {t}"
    
    assert len(IntentType) == 8


def test_intent_dataclass():
    """测试Intent数据类"""
    from src.agents.intent_recognizer import Intent, IntentType
    
    intent = Intent(
        type=IntentType.CONTRACT_REVIEW,
        confidence=0.9,
        entities={"key": "value"},
        raw_text="审查合同",
        method="keyword"
    )
    
    assert intent.type == IntentType.CONTRACT_REVIEW
    assert intent.confidence == 0.9
    assert intent.entities == {"key": "value"}
    
    d = intent.to_dict()
    assert d["type"] == "contract_review"
    assert d["confidence"] == 0.9


def test_recognize_contract_review():
    """测试识别合同审查意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    # 明确的合同审查意图
    intent = recognizer.recognize("帮我审查这份合同")
    assert intent.type == IntentType.CONTRACT_REVIEW
    assert intent.confidence > 0.3
    
    # 长文本合同审查
    long_text = "请审查以下合同内容：" + "这是一份技术服务合同，甲方为ABC公司。" * 10
    intent = recognizer.recognize(long_text)
    assert intent.type == IntentType.CONTRACT_REVIEW


def test_recognize_clause_analysis():
    """测试识别条款分析意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("请分析第三条条款")
    assert intent.type == IntentType.CLAUSE_ANALYSIS
    assert intent.confidence > 0


def test_recognize_risk_assessment():
    """测试识别风险评估意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("帮我评估一下这份合同的风险")
    assert intent.type == IntentType.RISK_ASSESSMENT
    assert intent.confidence > 0


def test_recognize_compliance_check():
    """测试识别合规检查意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("检查这份合同是否符合法律法规")
    assert intent.type == IntentType.COMPLIANCE_CHECK
    assert intent.confidence > 0


def test_recognize_report_generation():
    """测试识别报告生成意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("生成一份审查报告")
    assert intent.type == IntentType.REPORT_GENERATION
    assert intent.confidence > 0


def test_recognize_question():
    """测试识别问题回答意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("请问什么是违约责任？")
    assert intent.type == IntentType.QUESTION_ANSWER
    assert intent.confidence > 0


def test_recognize_greeting():
    """测试识别问候意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("你好")
    assert intent.type == IntentType.GREETING
    assert intent.confidence > 0


def test_recognize_empty_input():
    """测试空输入"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("")
    assert intent.type == IntentType.UNKNOWN
    assert intent.confidence == 0.0
    
    intent = recognizer.recognize("   ")
    assert intent.type == IntentType.UNKNOWN


def test_recognize_unknown():
    """测试未知意图"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    intent = recognizer.recognize("今天天气真好")
    assert intent.type == IntentType.UNKNOWN


def test_batch_recognize():
    """测试批量意图识别"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    texts = [
        "你好",
        "帮我审查合同",
        "评估风险",
        "什么是违约金？",
    ]
    
    intents = recognizer.batch_recognize(texts)
    assert len(intents) == 4
    assert intents[0].type == IntentType.GREETING
    assert intents[1].type == IntentType.CONTRACT_REVIEW
    assert intents[2].type == IntentType.RISK_ASSESSMENT
    assert intents[3].type == IntentType.QUESTION_ANSWER


def test_context_influence():
    """测试上下文对意图识别的影响"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    # 带有合同文本上下文
    context = {"has_contract_text": True, "last_intent": "contract_review"}
    intent = recognizer.recognize("帮我看看风险", context)
    # 应该识别为风险评估
    assert intent.type == IntentType.RISK_ASSESSMENT


def test_custom_keyword_rule():
    """测试自定义关键词规则"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="keyword")
    
    # 添加自定义规则
    recognizer.add_keyword_rule(
        IntentType.CONTRACT_REVIEW,
        keywords=["审合同", "过合同"],
        patterns=[r"过.{0,3}合同"]
    )
    
    intent = recognizer.recognize("帮我过一下合同")
    assert intent.type == IntentType.CONTRACT_REVIEW


def test_supported_intents():
    """测试获取支持的意图列表"""
    from src.agents.intent_recognizer import IntentRecognizer
    
    recognizer = IntentRecognizer(mode="keyword")
    intents = recognizer.get_supported_intents()
    
    assert isinstance(intents, list)
    assert len(intents) == 8
    
    types = [i["type"] for i in intents]
    assert "contract_review" in types
    assert "greeting" in types


def test_hybrid_mode_without_llm():
    """测试hybrid模式（无LLM回退到关键词）"""
    from src.agents.intent_recognizer import IntentRecognizer, IntentType
    
    recognizer = IntentRecognizer(mode="hybrid", llm=None)
    
    intent = recognizer.recognize("帮我审查这份合同")
    assert intent.type == IntentType.CONTRACT_REVIEW


# ==================== 对话上下文测试 ====================

def test_conversation_context_import():
    """测试对话上下文导入"""
    from src.agents.conversation_context import (
        ConversationContext, ConversationManager, ConversationState,
        Message, TurnContext
    )
    assert ConversationContext is not None
    assert ConversationManager is not None
    assert ConversationState is not None


def test_conversation_state_enum():
    """测试对话状态枚举"""
    from src.agents.conversation_context import ConversationState
    
    expected = ["idle", "collecting", "processing", "waiting_confirm", "completed", "error"]
    for s in expected:
        assert ConversationState(s), f"状态不存在: {s}"


def test_message_dataclass():
    """测试Message数据类"""
    from src.agents.conversation_context import Message
    
    msg = Message(role="user", content="你好")
    assert msg.role == "user"
    assert msg.content == "你好"
    assert msg.timestamp  # 自动生成
    
    d = msg.to_dict()
    assert d["role"] == "user"
    assert d["content"] == "你好"


def test_context_creation():
    """测试创建对话上下文"""
    from src.agents.conversation_context import ConversationContext, ConversationState
    
    ctx = ConversationContext()
    assert ctx.session_id  # 自动生成UUID
    assert ctx.state == ConversationState.IDLE
    
    ctx2 = ConversationContext(session_id="test-123")
    assert ctx2.session_id == "test-123"


def test_context_message_flow():
    """测试对话上下文消息流"""
    from src.agents.conversation_context import ConversationContext, ConversationState
    
    ctx = ConversationContext(session_id="test-flow")
    
    # 用户消息
    ctx.add_user_message("你好")
    assert ctx.state == ConversationState.COLLECTING
    assert len(ctx.get_messages()) == 1
    
    # 助手回复
    ctx.add_assistant_message("你好！有什么可以帮您？")
    assert ctx.state == ConversationState.COMPLETED
    assert len(ctx.get_messages()) == 2
    
    # 第二轮
    ctx.add_user_message("帮我审查合同")
    assert ctx.state == ConversationState.COLLECTING
    assert len(ctx.get_messages()) == 3
    
    messages = ctx.get_messages()
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_context_intent_chain():
    """测试意图链"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-intent")
    
    ctx.add_user_message("你好")
    ctx.set_current_intent("greeting", 0.9)
    
    ctx.add_assistant_message("你好！")
    ctx.add_user_message("帮我审查合同")
    ctx.set_current_intent("contract_review", 0.8)
    
    chain = ctx.get_intent_chain()
    assert chain == ["greeting", "contract_review"]
    assert ctx.get_last_intent() == "contract_review"


def test_context_agent_results():
    """测试Agent结果管理"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-results")
    
    ctx.add_user_message("审查合同")
    ctx.set_current_intent("contract_review", 0.9)
    
    # 设置Agent结果
    ctx.set_agent_result("document_parser", {"type": "技术服务合同"})
    ctx.set_agent_result("risk_assessor", {"risks": [{"level": "high"}]})
    
    # 获取结果
    assert ctx.get_agent_result("document_parser") == {"type": "技术服务合同"}
    assert ctx.get_agent_result("risk_assessor") == {"risks": [{"level": "high"}]}
    
    all_results = ctx.get_all_results()
    assert "document_parser" in all_results
    assert "risk_assessor" in all_results


def test_context_file_upload():
    """测试文件上传"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-upload")
    
    ctx.add_uploaded_file("contract.txt", "合同内容...", "txt")
    
    files = ctx.get_uploaded_files()
    assert len(files) == 1
    assert files[0]["filename"] == "contract.txt"
    
    # 合同文本应该自动存储
    assert ctx.get_contract_text() == "合同内容..."


def test_context_llm_context():
    """测试LLM上下文构建"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-llm")
    
    ctx.add_user_message("帮我审查合同")
    ctx.set_current_intent("contract_review", 0.9)
    ctx.add_uploaded_file("contract.txt", "合同内容..." * 20, "txt")
    
    llm_context = ctx.build_llm_context()
    assert isinstance(llm_context, str)
    assert "test-llm" in llm_context
    assert "contract_review" in llm_context


def test_context_task_context():
    """测试任务上下文构建"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-task")
    ctx.add_uploaded_file("contract.txt", "合同内容", "txt")
    ctx.set_agent_result("parser", {"type": "test"})
    
    task_ctx = ctx.build_task_context()
    assert task_ctx["session_id"] == "test-task"
    assert task_ctx["contract_text"] == "合同内容"
    assert "parser" in task_ctx["previous_results"]


def test_context_serialization():
    """测试上下文序列化和反序列化"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-serialize")
    ctx.add_user_message("你好")
    ctx.set_current_intent("greeting", 0.9)
    ctx.add_assistant_message("你好！")
    ctx.set_agent_result("test", {"key": "value"})
    
    # 序列化
    data = ctx.to_dict()
    assert data["session_id"] == "test-serialize"
    assert len(data["messages"]) == 2
    assert data["intent_chain"] == ["greeting"]
    
    # 反序列化
    ctx2 = ConversationContext.from_dict(data)
    assert ctx2.session_id == "test-serialize"
    assert len(ctx2.get_messages()) == 2
    assert ctx2.get_last_intent() == "greeting"


def test_context_persistence():
    """测试上下文文件持久化"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-persist")
    ctx.add_user_message("测试持久化")
    ctx.set_current_intent("test", 0.5)
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = f.name
    
    try:
        ctx.save_to_file(temp_path)
        
        ctx2 = ConversationContext.load_from_file(temp_path)
        assert ctx2 is not None
        assert ctx2.session_id == "test-persist"
        assert len(ctx2.get_messages()) == 1
    finally:
        os.unlink(temp_path)


def test_context_clear():
    """测试清空上下文"""
    from src.agents.conversation_context import ConversationContext, ConversationState
    
    ctx = ConversationContext(session_id="test-clear")
    ctx.add_user_message("测试")
    ctx.set_current_intent("test", 0.5)
    ctx.add_uploaded_file("test.txt", "内容", "txt")
    
    ctx.clear()
    
    assert ctx.state == ConversationState.IDLE
    assert len(ctx.get_messages()) == 0
    assert len(ctx.get_intent_chain()) == 0
    assert ctx.get_contract_text() is None


def test_context_status():
    """测试获取上下文状态"""
    from src.agents.conversation_context import ConversationContext
    
    ctx = ConversationContext(session_id="test-status")
    ctx.add_user_message("测试")
    ctx.set_current_intent("test", 0.5)
    
    status = ctx.get_status()
    assert status["session_id"] == "test-status"
    assert status["turn_count"] == 0  # 还没有助手回复
    assert status["total_messages"] == 1
    assert "test" in status["intent_chain"]


# ==================== 对话管理器测试 ====================

def test_conversation_manager():
    """测试对话管理器"""
    from src.agents.conversation_context import ConversationManager
    
    manager = ConversationManager()
    
    # 获取或创建会话
    ctx1 = manager.get_or_create("session-1")
    assert ctx1.session_id == "session-1"
    
    # 获取同一会话
    ctx2 = manager.get_or_create("session-1")
    assert ctx1 is ctx2  # 应该是同一个对象
    
    # 列出会话
    sessions = manager.list_sessions()
    assert len(sessions) == 1
    
    # 移除会话
    manager.remove("session-1")
    assert manager.get_active_count() == 0


def test_conversation_manager_max_sessions():
    """测试对话管理器最大会话数"""
    from src.agents.conversation_context import ConversationManager
    
    manager = ConversationManager(max_sessions=3)
    
    for i in range(5):
        manager.get_or_create(f"session-{i}")
    
    # 应该只保留最近3个
    assert manager.get_active_count() == 3


# ==================== 模块导出测试 ====================

def test_agents_module_export():
    """测试Agent模块导出"""
    from src.agents import (
        IntentRecognizer, IntentType, Intent,
        ConversationContext, ConversationManager, ConversationState,
        Message, TurnContext
    )
    assert IntentRecognizer is not None
    assert ConversationContext is not None


# ==================== 测试运行器 ====================

def run_all_tests():
    """运行所有意图识别测试"""
    print("\n" + "=" * 60)
    print("📋 Day 22: 意图识别与Agent路由测试")
    print("=" * 60)
    
    tests = [
        # 意图识别器测试
        ("意图识别器导入", test_intent_recognizer_import),
        ("意图类型枚举", test_intent_type_enum),
        ("Intent数据类", test_intent_dataclass),
        ("识别-合同审查", test_recognize_contract_review),
        ("识别-条款分析", test_recognize_clause_analysis),
        ("识别-风险评估", test_recognize_risk_assessment),
        ("识别-合规检查", test_recognize_compliance_check),
        ("识别-报告生成", test_recognize_report_generation),
        ("识别-问题回答", test_recognize_question),
        ("识别-问候", test_recognize_greeting),
        ("识别-空输入", test_recognize_empty_input),
        ("识别-未知意图", test_recognize_unknown),
        ("批量识别", test_batch_recognize),
        ("上下文影响", test_context_influence),
        ("自定义关键词规则", test_custom_keyword_rule),
        ("支持的意图列表", test_supported_intents),
        ("Hybrid模式无LLM", test_hybrid_mode_without_llm),
        
        # 对话上下文测试
        ("对话上下文导入", test_conversation_context_import),
        ("对话状态枚举", test_conversation_state_enum),
        ("Message数据类", test_message_dataclass),
        ("创建对话上下文", test_context_creation),
        ("消息流", test_context_message_flow),
        ("意图链", test_context_intent_chain),
        ("Agent结果管理", test_context_agent_results),
        ("文件上传", test_context_file_upload),
        ("LLM上下文构建", test_context_llm_context),
        ("任务上下文构建", test_context_task_context),
        ("序列化反序列化", test_context_serialization),
        ("文件持久化", test_context_persistence),
        ("清空上下文", test_context_clear),
        ("获取状态", test_context_status),
        
        # 对话管理器测试
        ("对话管理器", test_conversation_manager),
        ("最大会话数", test_conversation_manager_max_sessions),
        
        # 模块导出测试
        ("Agent模块导出", test_agents_module_export),
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
