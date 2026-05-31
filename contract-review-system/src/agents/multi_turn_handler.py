"""
多轮对话处理器 - 管理完整的多轮对话流程

功能：
- 对话历史存储和检索
- 上下文注入（历史对话 + 上传文件 + Agent结果）
- 意图路由到对应Agent
- 追问场景支持（解析→风险→修改建议→报告）
- 对话状态管理
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .intent_recognizer import IntentRecognizer, IntentType, Intent
from .conversation_context import ConversationContext, ConversationManager, ConversationState

logger = logging.getLogger(__name__)


# ==================== 意图到Agent的路由映射 ====================

INTENT_AGENT_ROUTING: Dict[IntentType, Dict[str, Any]] = {
    IntentType.CONTRACT_REVIEW: {
        "agent": "coordinator",
        "description": "完整合同审查",
        "requires_contract": True,
    },
    IntentType.CLAUSE_ANALYSIS: {
        "agent": "clause_analyst",
        "description": "条款分析",
        "requires_contract": True,
    },
    IntentType.RISK_ASSESSMENT: {
        "agent": "risk_assessor",
        "description": "风险评估",
        "requires_contract": True,
    },
    IntentType.COMPLIANCE_CHECK: {
        "agent": "compliance_checker",
        "description": "合规检查",
        "requires_contract": True,
    },
    IntentType.REPORT_GENERATION: {
        "agent": "report_generator",
        "description": "报告生成",
        "requires_contract": False,  # 可以使用缓存的结果
    },
    IntentType.QUESTION_ANSWER: {
        "agent": "coordinator",
        "description": "问题回答",
        "requires_contract": False,
    },
    IntentType.GREETING: {
        "agent": "system",
        "description": "问候",
        "requires_contract": False,
    },
    IntentType.UNKNOWN: {
        "agent": "coordinator",
        "description": "未知意图",
        "requires_contract": False,
    },
}

# ==================== 追问场景的上下文规则 ====================

FOLLOW_UP_RULES: Dict[str, List[str]] = {
    "risk_after_parse": {
        "trigger_intent": IntentType.RISK_ASSESSMENT,
        "required_previous": ["document_parser"],
        "context_inject": ["parsed_result"],
    },
    "clause_after_risk": {
        "trigger_intent": IntentType.CLAUSE_ANALYSIS,
        "required_previous": ["risk_assessor"],
        "context_inject": ["risk_result"],
    },
    "report_after_analysis": {
        "trigger_intent": IntentType.REPORT_GENERATION,
        "required_previous": ["risk_assessor", "clause_analyst"],
        "context_inject": ["all_results"],
    },
}


class MultiTurnHandler:
    """
    多轮对话处理器

    管理完整的多轮对话流程，包括：
    - 消息接收和意图识别
    - 上下文构建和注入
    - Agent路由和执行
    - 结果存储和回复生成
    """

    def __init__(
        self,
        intent_recognizer: Optional[IntentRecognizer] = None,
        conversation_manager: Optional[ConversationManager] = None,
    ):
        """
        初始化多轮对话处理器

        Args:
            intent_recognizer: 意图识别器（不提供则使用默认keyword模式）
            conversation_manager: 对话管理器（不提供则使用默认实例）
        """
        self.intent_recognizer = intent_recognizer or IntentRecognizer(mode="keyword")
        self.conversation_manager = conversation_manager or ConversationManager()
        self._agent_callbacks: Dict[str, callable] = {}

        logger.info("多轮对话处理器初始化")

    def register_agent_callback(self, agent_name: str, callback: callable):
        """
        注册Agent执行回调

        Args:
            agent_name: Agent名称
            callback: 异步回调函数，接收task_context参数
        """
        self._agent_callbacks[agent_name] = callback
        logger.info(f"注册Agent回调: {agent_name}")

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
            user_message: 用户消息文本
            contract_text: 合同文本（可选，上传文件时提供）
            file_info: 文件信息（可选，包含filename、type等）

        Returns:
            处理结果字典，包含intent、agent、result、response等
        """
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

        # 4. 识别意图（带上下文）
        intent_context = ctx.get_intent_context()
        intent = self.intent_recognizer.recognize(user_message, intent_context)
        ctx.set_current_intent(intent.type.value, intent.confidence)

        logger.info(f"意图识别: {intent.type.value} (confidence={intent.confidence:.2f})")

        # 5. 构建Agent任务上下文
        task_context = ctx.build_task_context()
        task_context["intent"] = intent.to_dict()
        task_context["user_message"] = user_message

        # 6. 注入追问上下文
        task_context = self._inject_follow_up_context(task_context, intent, ctx)

        # 7. 路由到对应的Agent
        routing_info = self._get_routing(intent.type)
        agent_name = routing_info["agent"]

        # 8. 检查是否需要合同文本
        if routing_info.get("requires_contract") and not task_context.get("contract_text"):
            response = "请先上传或提供合同文本，然后我再帮您进行分析。"
            ctx.add_assistant_message(response)
            return {
                "session_id": session_id,
                "intent": intent.to_dict(),
                "agent": agent_name,
                "result": None,
                "response": response,
                "needs_contract": True,
            }

        # 9. 执行Agent
        result = await self._execute_agent(agent_name, task_context)

        # 10. 存储结果到上下文
        ctx.set_agent_result(agent_name, result)

        # 11. 生成回复
        response = self._format_response(intent.type, result, ctx, agent_name)
        ctx.add_assistant_message(response)

        return {
            "session_id": session_id,
            "intent": intent.to_dict(),
            "agent": agent_name,
            "result": result,
            "response": response,
            "context_summary": self._get_context_summary(ctx),
        }

    def _get_routing(self, intent_type: IntentType) -> Dict[str, Any]:
        """获取意图对应的路由信息"""
        return INTENT_AGENT_ROUTING.get(intent_type, INTENT_AGENT_ROUTING[IntentType.UNKNOWN])

    def _inject_follow_up_context(
        self,
        task_context: Dict[str, Any],
        intent: Intent,
        ctx: ConversationContext,
    ) -> Dict[str, Any]:
        """
        注入追问上下文

        根据当前意图和历史Agent结果，自动注入相关上下文。
        """
        all_results = ctx.get_all_results()

        if not all_results:
            return task_context

        # 风险评估追问：注入解析结果
        if intent.type == IntentType.RISK_ASSESSMENT:
            if "document_parser" in all_results:
                task_context["parsed_result"] = all_results["document_parser"]
                logger.debug("注入解析结果到风险评估上下文")

        # 条款分析追问：注入风险结果
        if intent.type == IntentType.CLAUSE_ANALYSIS:
            if "risk_assessor" in all_results:
                task_context["risk_result"] = all_results["risk_assessor"]
                logger.debug("注入风险结果到条款分析上下文")

        # 报告生成：注入所有结果
        if intent.type == IntentType.REPORT_GENERATION:
            task_context["all_previous_results"] = all_results
            logger.debug("注入所有分析结果到报告生成上下文")

        return task_context

    async def _execute_agent(
        self, agent_name: str, task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行Agent

        优先使用注册的回调函数，否则返回模拟结果。
        """
        if agent_name in self._agent_callbacks:
            try:
                callback = self._agent_callbacks[agent_name]
                result = await callback(task_context)
                logger.info(f"Agent执行完成: {agent_name}")
                return result
            except Exception as e:
                logger.error(f"Agent执行失败: {agent_name} - {e}")
                return {
                    "status": "error",
                    "agent": agent_name,
                    "error": str(e),
                }

        # 模拟执行结果
        return self._get_simulated_result(agent_name, task_context)

    def _get_simulated_result(
        self, agent_name: str, task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取模拟执行结果（用于测试和演示）"""
        intent_info = task_context.get("intent", {})
        intent_type = intent_info.get("type", "unknown")

        simulated_results = {
            "coordinator": {
                "status": "completed",
                "agent": "coordinator",
                "summary": f"已完成协调处理，意图: {intent_type}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "document_parser": {
                "status": "completed",
                "agent": "document_parser",
                "contract_type": "技术服务合同",
                "parties": {"party_a": "甲方公司", "party_b": "乙方公司"},
                "amount": {"value": 100000, "currency": "CNY"},
                "duration": "2024-01-01 至 2025-12-31",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "clause_analyst": {
                "status": "completed",
                "agent": "clause_analyst",
                "clauses_analyzed": 5,
                "issues_found": 2,
                "key_clauses": ["违约责任", "保密条款", "付款条件"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "risk_assessor": {
                "status": "completed",
                "agent": "risk_assessor",
                "risk_level": "medium",
                "risks": [
                    {"level": "high", "description": "违约金比例偏高"},
                    {"level": "medium", "description": "付款周期较长"},
                    {"level": "low", "description": "保密期限偏短"},
                ],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "compliance_checker": {
                "status": "completed",
                "agent": "compliance_checker",
                "compliance_score": 85,
                "issues": ["缺少争议解决条款"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "report_generator": {
                "status": "completed",
                "agent": "report_generator",
                "report_type": "综合审查报告",
                "sections": ["合同概要", "条款分析", "风险评估", "合规检查", "修改建议"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "system": {
                "status": "completed",
                "agent": "system",
                "message": "您好！我是智能合同审查助手。",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

        return simulated_results.get(agent_name, {
            "status": "completed",
            "agent": agent_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    def _format_response(
        self,
        intent_type: IntentType,
        result: Dict[str, Any],
        ctx: ConversationContext,
        agent_name: str,
    ) -> str:
        """
        根据意图类型和Agent结果生成用户友好的回复

        Args:
            intent_type: 意图类型
            result: Agent执行结果
            ctx: 对话上下文
            agent_name: Agent名称

        Returns:
            格式化的回复文本
        """
        if not result:
            return "抱歉，处理过程中出现了问题。"

        status = result.get("status", "unknown")

        if intent_type == IntentType.GREETING:
            return result.get("message", "您好！我是智能合同审查助手，请问有什么可以帮助您的？")

        if intent_type == IntentType.CONTRACT_REVIEW:
            if status == "completed":
                return (
                    f"合同审查已完成。\n\n"
                    f"📊 审查摘要：{result.get('summary', '无')}\n"
                    f"如需进一步分析，请告诉我具体需求，例如：\n"
                    f"- 评估风险\n"
                    f"- 分析条款\n"
                    f"- 检查合规性\n"
                    f"- 生成报告"
                )
            elif status == "error":
                return f"合同审查遇到问题：{result.get('error', '未知错误')}"

        if intent_type == IntentType.RISK_ASSESSMENT:
            if status == "completed":
                risk_level = result.get("risk_level", "unknown")
                risks = result.get("risks", [])
                level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")
                response = f"⚠️ 风险评估完成 {level_emoji}\n\n"
                response += f"风险等级: {risk_level.upper()}\n\n"
                for i, risk in enumerate(risks, 1):
                    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("level"), "⚪")
                    response += f"{i}. {emoji} {risk.get('description', '无描述')}\n"
                response += "\n如需详细分析某个风险点，请告诉我。"
                return response

        if intent_type == IntentType.CLAUSE_ANALYSIS:
            if status == "completed":
                clauses = result.get("key_clauses", [])
                issues = result.get("issues_found", 0)
                response = f"📋 条款分析完成\n\n"
                response += f"分析条款数: {result.get('clauses_analyzed', 0)}\n"
                response += f"发现问题: {issues} 个\n\n"
                if clauses:
                    response += "关键条款:\n"
                    for clause in clauses:
                        response += f"- {clause}\n"
                return response

        if intent_type == IntentType.COMPLIANCE_CHECK:
            if status == "completed":
                score = result.get("compliance_score", 0)
                issues = result.get("issues", [])
                response = f"✅ 合规检查完成\n\n"
                response += f"合规评分: {score}/100\n\n"
                if issues:
                    response += "需要改进:\n"
                    for issue in issues:
                        response += f"- ⚠️ {issue}\n"
                else:
                    response += "未发现合规问题。\n"
                return response

        if intent_type == IntentType.REPORT_GENERATION:
            if status == "completed":
                sections = result.get("sections", [])
                response = f"📊 审查报告已生成\n\n"
                response += f"报告类型: {result.get('report_type', '综合报告')}\n"
                response += "包含章节:\n"
                for section in sections:
                    response += f"- ✅ {section}\n"
                return response

        if intent_type == IntentType.QUESTION_ANSWER:
            if status == "completed":
                return result.get("answer", result.get("summary", "让我为您解答这个问题。"))

        # 默认回复
        return f"已处理您的请求（意图: {intent_type.value}）。如需其他帮助，请告诉我。"

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
        """获取支持的意图和路由信息"""
        result = []
        for intent_type, routing in INTENT_AGENT_ROUTING.items():
            result.append({
                "intent": intent_type.value,
                "agent": routing["agent"],
                "description": routing["description"],
                "requires_contract": routing["requires_contract"],
            })
        return result
