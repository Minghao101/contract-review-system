"""
多轮对话处理器 - 基于LangGraph工作流

职责：
- 意图识别
- LangGraph工作流集成
- 对话历史管理
- 流式输出支持
- Human-in-the-loop（可选）
"""
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .intent_recognizer import IntentRecognizer, IntentType
from .conversation_context import ConversationContext, ConversationManager, ConversationState

logger = logging.getLogger(__name__)


class MultiTurnHandler:
    """
    多轮对话处理器（基于LangGraph工作流）

    核心职责：
    1. 意图识别
    2. 调用LangGraph工作流执行
    3. 对话历史管理
    4. 流式输出支持
    """

    def __init__(
        self,
        intent_recognizer: Optional[IntentRecognizer] = None,
        conversation_manager: Optional[ConversationManager] = None,
        enable_human_review: bool = False,
    ):
        """
        初始化多轮对话处理器

        Args:
            intent_recognizer: 意图识别器
            conversation_manager: 对话管理器
            enable_human_review: 是否启用人工审批
        """
        self.intent_recognizer = intent_recognizer or IntentRecognizer()
        self.conversation_manager = conversation_manager or ConversationManager()
        self._agents: Dict[str, BaseAgent] = {}
        self._enable_human_review = enable_human_review
        self._workflow = None

        logger.info("多轮对话处理器初始化（LangGraph工作流模式）")

    def _ensure_workflow(self):
        """确保工作流已初始化"""
        if self._workflow is None:
            from src.workflow.multi_turn_workflow import MultiTurnWorkflow
            self._workflow = MultiTurnWorkflow(enable_human_review=self._enable_human_review)

    def register_agent(self, agent: BaseAgent):
        """注册Agent实例"""
        self._agents[agent.agent_id] = agent
        logger.info(f"注册Agent: {agent.name} ({agent.agent_id})")

    def register_agents(self, agents: List[BaseAgent]):
        """批量注册Agent"""
        for agent in agents:
            self.register_agent(agent)

    async def handle_message(
        self,
        session_id: str,
        user_message: str,
        contract_text: Optional[str] = None,
        file_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        处理用户消息（多轮对话核心方法）

        Args:
            session_id: 会话ID
            user_message: 用户消息
            contract_text: 合同文本
            file_info: 文件信息

        Returns:
            处理结果
        """
        self._ensure_workflow()

        # 1. 获取或创建会话上下文
        ctx = self.conversation_manager.get_or_create(session_id)

        # 2. 添加用户消息
        ctx.add_user_message(user_message)

        # 3. 如果有合同文本，添加到上下文
        if contract_text:
            filename = "contract.txt"
            file_type = "txt"
            if file_info:
                filename = file_info.get("filename", filename)
                file_type = file_info.get("type", file_type)
            ctx.add_uploaded_file(filename, contract_text, file_type)

        # 4. 获取对话历史
        messages = ctx.get_messages()

        # 5. 执行工作流
        try:
            effective_contract = contract_text or ctx.get_contract_text() or ""
            result = await self._workflow.run(
                user_input=user_message,
                session_id=session_id,
                contract_text=effective_contract,
                contract_type=file_info.get("contract_type", "general") if file_info else "general",
                messages=messages,
                auto_approve=True,
            )

            # 6. 提取结果
            response = result.get("response", "")
            intent = result.get("intent", {})
            agent_results = result.get("agent_results", {})

            # 7. 更新会话上下文
            ctx.add_assistant_message(response)
            for agent_name, agent_result in agent_results.items():
                ctx.set_agent_result(agent_name, agent_result)

            return {
                "session_id": session_id,
                "intent": intent,
                "agents": list(agent_results.keys()),
                "result": agent_results,
                "response": response,
                "context_summary": self._get_context_summary(ctx),
            }

        except Exception as e:
            logger.error(f"工作流执行失败: {e}", exc_info=True)
            response = f"处理过程中出现错误: {str(e)}"
            ctx.add_assistant_message(response)
            return {
                "session_id": session_id,
                "intent": {"type": IntentType.UNKNOWN.value},
                "agents": [],
                "result": None,
                "response": response,
                "error": str(e),
            }

    async def handle_message_stream(
        self,
        session_id: str,
        user_message: str,
        contract_text: Optional[str] = None,
        file_info: Optional[Dict[str, Any]] = None,
    ):
        """
        流式处理用户消息

        Args:
            session_id: 会话ID
            user_message: 用户消息
            contract_text: 合同文本
            file_info: 文件信息

        Yields:
            事件字典
        """
        self._ensure_workflow()

        # 1. 获取或创建会话上下文
        ctx = self.conversation_manager.get_or_create(session_id)
        ctx.add_user_message(user_message)

        # 2. 如果有合同文本，添加到上下文
        if contract_text:
            filename = "contract.txt"
            file_type = "txt"
            if file_info:
                filename = file_info.get("filename", filename)
                file_type = file_info.get("type", file_type)
            ctx.add_uploaded_file(filename, contract_text, file_type)

        # 3. 获取对话历史
        messages = ctx.get_messages()

        # 4. 流式执行工作流
        effective_contract = contract_text or ctx.get_contract_text() or ""
        try:
            async for event in self._workflow.stream(
                user_input=user_message,
                session_id=session_id,
                contract_text=effective_contract,
                contract_type=file_info.get("contract_type", "general") if file_info else "general",
                messages=messages,
            ):
                if not isinstance(event, dict):
                    continue
                yield event

                # 如果是最终结果，更新会话上下文
                try:
                    if event.get("event") == "result":
                        response = event.get("data", {}).get("content", "")
                        if response:
                            ctx.add_assistant_message(response)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"流式执行失败: {e}", exc_info=True)
            yield {"event": "error", "data": {"message": f"处理过程中出现错误: {str(e)}"}}
            yield {"event": "done", "data": {}}

    async def resume_workflow(
        self,
        session_id: str,
        user_reply: str,
    ) -> Dict[str, Any]:
        """
        恢复被interrupt暂停的工作流

        Args:
            session_id: 会话ID
            user_reply: 用户回复内容

        Returns:
            处理结果
        """
        self._ensure_workflow()

        try:
            result = await self._workflow.resume(session_id=session_id, user_reply=user_reply)
            return result
        except Exception as e:
            logger.error(f"工作流恢复失败: {e}", exc_info=True)
            return {"error": str(e)}

    def _get_context_summary(self, ctx: ConversationContext) -> Dict[str, Any]:
        """获取上下文摘要"""
        all_results = ctx.get_all_results()
        return {
            "turn_count": len(ctx._turns),
            "intent_chain": ctx.get_intent_chain(),
            "completed_agents": list(all_results.keys()),
            "has_contract": bool(ctx.get_contract_text()),
            "state": ctx.state.value,
        }

    def get_session_history(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """获取会话历史"""
        ctx = self.conversation_manager.get_or_create(session_id)
        return ctx.get_messages()

    def get_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话上下文摘要"""
        sessions = self.conversation_manager.list_sessions()
        for s in sessions:
            if s["session_id"] == session_id:
                ctx = self.conversation_manager.get_or_create(session_id)
                return {
                    "session_id": session_id,
                    "state": ctx.state.value,
                    "intent_chain": ctx.get_intent_chain(),
                    "agent_results": list(ctx.get_all_results().keys()),
                    "has_contract": bool(ctx.get_contract_text()),
                    "message_count": len(ctx.get_messages()),
                }
        return None

    def clear_session(self, session_id: str) -> bool:
        """清空会话上下文"""
        ctx = self.conversation_manager.get_or_create(session_id)
        ctx.clear()
        logger.info(f"会话已清空: {session_id}")
        return True

    def get_supported_intents(self) -> List[Dict[str, Any]]:
        """获取支持的意图信息"""
        return [
            {"intent": "contract_review", "description": "完整合同审查", "requires_contract": True},
            {"intent": "risk_assessment", "description": "风险评估", "requires_contract": True},
            {"intent": "clause_analysis", "description": "条款分析", "requires_contract": True},
            {"intent": "compliance_check", "description": "合规检查", "requires_contract": True},
            {"intent": "modify_contract", "description": "修改合同条款", "requires_contract": True},
            {"intent": "report_generation", "description": "报告生成", "requires_contract": False},
            {"intent": "question_answer", "description": "问题回答", "requires_contract": False},
            {"intent": "greeting", "description": "问候", "requires_contract": False},
        ]

    def get_workflow_info(self) -> Dict[str, Any]:
        """获取工作流信息"""
        self._ensure_workflow()
        return self._workflow.get_workflow_info()
