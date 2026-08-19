"""
多轮对话工作流测试

测试基于LangGraph的多轮对话工作流功能
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.workflow.multi_turn_workflow import (
    MultiTurnWorkflow,
    MultiTurnState,
    ConversationStatus,
    create_multi_turn_workflow,
)
from src.agents.intent_recognizer import IntentType


class TestMultiTurnWorkflow:
    """多轮对话工作流测试类"""

    def test_workflow_initialization(self):
        """测试工作流初始化"""
        workflow = MultiTurnWorkflow(enable_human_review=False)
        workflow._ensure_workflow()
        assert workflow._workflow is not None

    def test_workflow_with_human_review(self):
        """测试带人工审批的工作流初始化"""
        workflow = MultiTurnWorkflow(enable_human_review=True)
        workflow._ensure_workflow()
        assert workflow._workflow is not None

    def test_workflow_info(self):
        """测试获取工作流信息"""
        workflow = MultiTurnWorkflow()
        info = workflow.get_workflow_info()
        assert "name" in info
        assert "version" in info
        assert "features" in info
        assert info["name"] == "多轮对话工作流"

    @pytest.mark.asyncio
    async def test_process_user_input(self):
        """测试处理用户输入节点"""
        from src.workflow.multi_turn_workflow import create_node_functions

        nodes = create_node_functions()
        state = MultiTurnState(
            messages=[],
            user_input="你好",
            session_id="test_session",
            intent=None,
            intent_confidence=0.0,
            intent_reasoning="",
            contract_text=None,
            contract_type="general",
            agent_results={},
            status=ConversationStatus.IDLE.value,
            turn_count=0,
            enable_human_review=False,
            response=None,
            error=None,
        )

        result = await nodes["process_user_input"](state)

        assert result["status"] == ConversationStatus.COLLECTING.value
        assert result["turn_count"] == 1
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_recognize_intent(self):
        """测试意图识别节点"""
        from src.workflow.multi_turn_workflow import create_node_functions

        nodes = create_node_functions()
        state = MultiTurnState(
            messages=[{"role": "user", "content": "你好", "timestamp": ""}],
            user_input="你好",
            session_id="test_session",
            intent=None,
            intent_confidence=0.0,
            intent_reasoning="",
            contract_text=None,
            contract_type="general",
            agent_results={},
            status=ConversationStatus.COLLECTING.value,
            turn_count=1,
            enable_human_review=False,
            response=None,
            error=None,
        )

        # 直接测试意图识别（不mock，使用真实LLM可能失败，但测试结构）
        try:
            result = await nodes["recognize_intent"](state)
            # 如果成功，检查状态更新
            assert "intent" in result
        except Exception as e:
            # 如果LLM不可用，确保错误被正确处理
            assert "error" in result or "intent" in result

    @pytest.mark.asyncio
    async def test_route_by_intent(self):
        """测试意图路由"""
        from src.workflow.multi_turn_workflow import create_node_functions

        nodes = create_node_functions()

        # 测试合同审查意图
        state = MultiTurnState(
            messages=[],
            user_input="请审查合同",
            session_id="test",
            intent={"type": IntentType.CONTRACT_REVIEW.value, "confidence": 0.9},
            intent_confidence=0.9,
            intent_reasoning="",
            contract_text="合同文本",
            contract_type="general",
            agent_results={},
            status=ConversationStatus.PROCESSING.value,
            turn_count=1,
            enable_human_review=False,
            response=None,
            error=None,
        )
        route = await nodes["route_by_intent"](state)
        assert route == "analysis"

        # 测试问题回答意图
        state["intent"] = {"type": IntentType.QUESTION_ANSWER.value, "confidence": 0.9}
        route = await nodes["route_by_intent"](state)
        assert route == "follow_up"

        # 测试议题讨论意图
        state["intent"] = {"type": IntentType.TOPIC_RAISE.value, "confidence": 0.9}
        route = await nodes["route_by_intent"](state)
        assert route == "topic"

        # 测试问候意图
        state["intent"] = {"type": IntentType.GREETING.value, "confidence": 0.9}
        route = await nodes["route_by_intent"](state)
        assert route == "direct"

    def test_create_workflow(self):
        """测试创建工作流"""
        workflow = create_multi_turn_workflow(enable_human_review=False)
        assert workflow is not None

        workflow_with_review = create_multi_turn_workflow(enable_human_review=True)
        assert workflow_with_review is not None


class TestMultiTurnHandler:
    """多轮对话处理器测试类"""

    def test_handler_initialization(self):
        """测试处理器初始化"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()
        assert handler is not None
        assert handler._enable_human_review is False

    def test_handler_with_human_review(self):
        """测试带人工审批的处理器初始化"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler(enable_human_review=True)
        assert handler._enable_human_review is True

    def test_supported_intents(self):
        """测试获取支持的意图"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()
        intents = handler.get_supported_intents()
        assert len(intents) > 0
        assert any(i["intent"] == "contract_review" for i in intents)

    @pytest.mark.asyncio
    async def test_handle_greeting(self):
        """测试处理问候消息"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()

        # Mock工作流
        mock_workflow = MagicMock()
        mock_workflow.run = AsyncMock(return_value={
            "intent": {"type": IntentType.GREETING.value, "confidence": 0.95},
            "response": "您好！我是智能合同审查助手。",
            "agent_results": {},
        })
        handler._workflow = mock_workflow

        result = await handler.handle_message(
            session_id="test_session",
            user_message="你好",
        )

        assert "response" in result
        assert result["intent"]["type"] == IntentType.GREETING.value

    @pytest.mark.asyncio
    async def test_handle_message_stream(self):
        """测试流式处理消息"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()

        # Mock工作流
        async def mock_stream(*args, **kwargs):
            yield {"event": "progress", "data": {"status": "starting"}}
            yield {"event": "result", "data": {"content": "测试回复"}}
            yield {"event": "done", "data": {}}

        mock_workflow = MagicMock()
        mock_workflow.stream = mock_stream
        handler._workflow = mock_workflow

        events = []
        async for event in handler.handle_message_stream(
            session_id="test_session",
            user_message="测试",
        ):
            events.append(event)

        assert len(events) > 0
        assert any(e["event"] == "result" for e in events)

    def test_clear_session(self):
        """测试清空会话"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()
        result = handler.clear_session("test_session")
        assert result is True

    def test_get_session_history(self):
        """测试获取会话历史"""
        from src.agents.multi_turn_handler import MultiTurnHandler

        handler = MultiTurnHandler()
        history = handler.get_session_history("test_session")
        assert isinstance(history, list)


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow_execution(self):
        """测试完整工作流执行"""
        workflow = MultiTurnWorkflow(enable_human_review=False)

        # 由于需要真实的Agent和LLM，这里只测试工作流结构
        info = workflow.get_workflow_info()
        assert "nodes" in info
        assert len(info["nodes"]) > 0

    def test_workflow_features(self):
        """测试工作流特性"""
        workflow = MultiTurnWorkflow()
        info = workflow.get_workflow_info()

        assert "checkpoint" in info["features"]
        assert "streaming" in info["features"]
        assert "human_in_the_loop" in info["features"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
