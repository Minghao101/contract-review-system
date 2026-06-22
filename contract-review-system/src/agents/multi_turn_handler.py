"""
多轮对话处理器 - 管理完整的多轮对话流程

功能：
- 对话历史存储和检索
- 上下文注入（历史对话 + 上传文件 + Agent结果）
- 意图路由到对应Agent（直接执行）
- 问候和未知意图直接处理（不需要Agent）
- 追问场景支持（解析→风险→修改建议→报告）
- 对话状态管理
"""
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .intent_recognizer import IntentRecognizer, IntentType, Intent
from .conversation_context import ConversationContext, ConversationManager, ConversationState
from src.utils.llm_factory import get_llm

logger = logging.getLogger(__name__)


# ==================== 意图到Agent的路由映射 ====================

INTENT_AGENT_ROUTING: Dict[IntentType, Dict[str, Any]] = {
    IntentType.CONTRACT_REVIEW: {
        "agents": ["document_parser", "clause_analyst", "risk_assessor", "compliance_checker"],
        "description": "完整合同审查（并行执行多个Agent）",
        "requires_contract": True,
        "parallel": True,
    },
    IntentType.CLAUSE_ANALYSIS: {
        "agents": ["clause_analyst"],
        "description": "条款分析",
        "requires_contract": True,
        "parallel": False,
    },
    IntentType.RISK_ASSESSMENT: {
        "agents": ["risk_assessor"],
        "description": "风险评估",
        "requires_contract": True,
        "parallel": False,
    },
    IntentType.COMPLIANCE_CHECK: {
        "agents": ["compliance_checker"],
        "description": "合规检查",
        "requires_contract": True,
        "parallel": False,
    },
    IntentType.REPORT_GENERATION: {
        "agents": ["report_generator"],
        "description": "报告生成",
        "requires_contract": False,
        "parallel": False,
    },
    IntentType.QUESTION_ANSWER: {
        "agents": [],
        "description": "问题回答（基于上下文直接回答）",
        "requires_contract": False,
        "parallel": False,
        "direct_response": True,
    },
    # 问候和未知意图不需要Agent，直接在handler中处理
    IntentType.GREETING: {
        "agents": [],
        "description": "问候",
        "requires_contract": False,
        "parallel": False,
        "direct_response": True,
    },
    IntentType.UNKNOWN: {
        "agents": [],
        "description": "未知意图",
        "requires_contract": False,
        "parallel": False,
        "direct_response": True,
    },
}


class MultiTurnHandler:
    """
    多轮对话处理器

    直接管理Agent执行，不经过CoordinatorAgent：
    - 消息接收和意图识别
    - 上下文构建和注入
    - 直接路由到对应Agent执行
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
            intent_recognizer: 意图识别器（不提供则使用默认实例）
            conversation_manager: 对话管理器（不提供则使用默认实例）
        """
        self.intent_recognizer = intent_recognizer or IntentRecognizer()
        self.conversation_manager = conversation_manager or ConversationManager()
        self._agents: Dict[str, BaseAgent] = {}

        logger.info("多轮对话处理器初始化")

    def register_agent(self, agent: BaseAgent):
        """
        注册Agent实例

        Args:
            agent: Agent实例
        """
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
        intent = await self.intent_recognizer.recognize(user_message, intent_context)
        ctx.set_current_intent(intent.type.value, intent.confidence)

        logger.info(f"意图识别: {intent.type.value} (confidence={intent.confidence:.2f})")

        # 5. 构建Agent任务上下文
        task_context = ctx.build_task_context()
        task_context["intent"] = intent.to_dict()
        task_context["user_message"] = user_message

        # 6. 注入追问上下文
        task_context = self._inject_follow_up_context(task_context, intent, ctx)

        # 7. 路由到对应的Agent（直接执行）
        routing_info = self._get_routing(intent.type)
        agent_names = routing_info["agents"]

        # 8. 处理问候、未知意图和问题回答（不需要Agent）
        if routing_info.get("direct_response"):
            if intent.type == IntentType.QUESTION_ANSWER:
                response = await self._answer_from_context(user_message, ctx)
            else:
                response = self._get_direct_response(intent.type)
            ctx.add_assistant_message(response)
            return {
                "session_id": session_id,
                "intent": intent.to_dict(),
                "agents": [],
                "result": None,
                "response": response,
                "context_summary": self._get_context_summary(ctx),
            }

        # 9. 检查是否需要合同文本
        if routing_info.get("requires_contract") and not task_context.get("contract_text"):
            response = "请先上传或提供合同文本，然后我再帮您进行分析。"
            ctx.add_assistant_message(response)
            return {
                "session_id": session_id,
                "intent": intent.to_dict(),
                "agents": agent_names,
                "result": None,
                "response": response,
                "needs_contract": True,
            }

        # 10. 执行Agent（直接调用Agent.process()）
        result = await self._execute_agents(agent_names, task_context, routing_info.get("parallel", False))

        # 11. 存储结果到上下文
        for agent_name in agent_names:
            if agent_name in result:
                ctx.set_agent_result(agent_name, result[agent_name])

        # 12. 生成回复
        response = self._format_response(intent.type, result, ctx)
        ctx.add_assistant_message(response)

        return {
            "session_id": session_id,
            "intent": intent.to_dict(),
            "agents": agent_names,
            "result": result,
            "response": response,
            "context_summary": self._get_context_summary(ctx),
        }

    def _get_routing(self, intent_type: IntentType) -> Dict[str, Any]:
        """获取意图对应的路由信息"""
        return INTENT_AGENT_ROUTING.get(intent_type, INTENT_AGENT_ROUTING[IntentType.UNKNOWN])

    def _get_direct_response(self, intent_type: IntentType) -> str:
        """
        获取问候和未知意图的直接回复

        Args:
            intent_type: 意图类型

        Returns:
            回复文本
        """
        if intent_type == IntentType.GREETING:
            return (
                "您好！我是智能合同审查助手，可以帮您：\n\n"
                "- 审查合同\n"
                "- 分析条款\n"
                "- 评估风险\n"
                "- 检查合规性\n"
                "- 生成报告\n\n"
                "请上传或粘贴合同文本，告诉我您需要什么帮助。"
            )

        # 未知意图
        return (
            "抱歉，我不太理解您的意思。您可以：\n\n"
            "- 上传合同文本进行审查\n"
            "- 告诉我具体需求（如：评估风险、分析条款）\n"
            "- 问我关于合同的问题"
        )

    async def _answer_from_context(self, user_message: str, ctx: ConversationContext) -> str:
        """
        基于上下文回答用户问题（使用LLM理解对话历史）

        Args:
            user_message: 用户问题
            ctx: 对话上下文

        Returns:
            回复文本
        """
        logger.info(f"追问处理: message={user_message[:50]}, session={ctx.session_id}")

        # 如果没有任何对话历史，提示用户
        messages = ctx.get_messages()
        logger.info(f"上下文消息数: {len(messages)}")
        if not messages:
            return "目前还没有进行过对话。请先上传合同文件，然后我可以帮你分析。"

        # 构建上下文：合同内容 + 对话历史
        context_parts = []

        # 1. 合同内容
        contract_text = ctx.get_contract_text()
        if contract_text:
            context_parts.append(f"=== 合同内容 ===\n{contract_text[:3000]}")
            logger.info(f"合同内容: {len(contract_text)}字")
        else:
            logger.warning("未找到合同内容")

        # 2. 对话历史
        context_parts.append("\n=== 对话历史 ===")
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            context_parts.append(f"{role}: {msg['content'][:500]}")

        context_str = "\n".join(context_parts)

        # 调用LLM回答
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm()
            messages = [
                SystemMessage(content="""你是一个合同审查助手。用户之前已经对合同进行了分析，现在在追问细节。

规则：
1. 根据提供的合同内容和对话历史回答用户问题
2. 对话历史中助手的回复包含了之前的分析结果，直接引用即可
3. 回答要简洁明了，直接回答问题
4. 如果上下文中没有相关信息，如实告知"""),
                HumanMessage(content=f"""{context_str}

用户问题：{user_message}""")
            ]

            response = await llm.ainvoke(messages)
            content = response.content
            # LLM可能返回content blocks列表（如thinking + text），提取文本部分
            if isinstance(content, list):
                text_parts = [block.get("text", "") for block in content
                              if isinstance(block, dict) and block.get("type") == "text"]
                content = "\n".join(text_parts) if text_parts else str(content)
            logger.info(f"LLM回答完成: {len(content)}字")
            return content

        except Exception as e:
            logger.error(f"LLM回答失败: {e}", exc_info=True)
            return f"抱歉，回答问题时出现错误。您可以尝试重新提问。"

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

    async def _execute_agents(
        self,
        agent_names: List[str],
        task_context: Dict[str, Any],
        parallel: bool = False
    ) -> Dict[str, Any]:
        """
        执行Agent（直接调用Agent.process()）

        Args:
            agent_names: 要执行的Agent名称列表
            task_context: 任务上下文
            parallel: 是否并行执行

        Returns:
            执行结果字典 {agent_name: result}
        """
        results = {}

        # 过滤出已注册的Agent
        agents_to_run = []
        for agent_name in agent_names:
            if agent_name in self._agents:
                agents_to_run.append((agent_name, self._agents[agent_name]))
            else:
                logger.warning(f"Agent未注册: {agent_name}")
                results[agent_name] = {
                    "status": "skipped",
                    "reason": "agent_not_registered"
                }

        if not agents_to_run:
            return results

        # 执行Agent
        if parallel and len(agents_to_run) > 1:
            # 并行执行
            import asyncio
            async_tasks = []
            for agent_name, agent in agents_to_run:
                async_tasks.append(self._execute_single_agent(agent_name, agent, task_context))

            task_results = await asyncio.gather(*async_tasks, return_exceptions=True)

            for (agent_name, _), result in zip(agents_to_run, task_results):
                if isinstance(result, Exception):
                    results[agent_name] = {
                        "status": "error",
                        "error": str(result)
                    }
                else:
                    results[agent_name] = result
        else:
            # 串行执行
            for agent_name, agent in agents_to_run:
                result = await self._execute_single_agent(agent_name, agent, task_context)
                results[agent_name] = result

        return results

    async def _execute_single_agent(
        self,
        agent_name: str,
        agent: BaseAgent,
        task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行单个Agent

        Args:
            agent_name: Agent名称
            agent: Agent实例
            task_context: 任务上下文

        Returns:
            执行结果
        """
        try:
            # 准备Agent输入
            task_input = self._prepare_agent_input(agent_name, task_context)

            # 直接调用agent.process()
            logger.info(f"开始执行Agent: {agent_name}")
            result = await agent.process(task_input)
            logger.info(f"Agent执行完成: {agent_name}")

            return {
                "status": "completed",
                "agent": agent_name,
                "result": result
            }
        except Exception as e:
            logger.error(f"Agent执行失败: {agent_name} - {e}")
            return {
                "status": "error",
                "agent": agent_name,
                "error": str(e)
            }

    def _prepare_agent_input(
        self,
        agent_name: str,
        task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        准备Agent输入参数

        根据不同Agent类型，从task_context中提取所需参数
        """
        contract_text = task_context.get("contract_text", "")
        contract_type = task_context.get("contract_type", "general")

        # 根据Agent类型准备不同的输入
        agent_inputs = {
            "document_parser": {
                "contract_text": contract_text,
                "contract_type": contract_type,
            },
            "clause_analyst": {
                "contract_text": contract_text,
                "review_focus": task_context.get("review_focus", []),
            },
            "risk_assessor": {
                "contract_text": contract_text,
                "contract_type": contract_type,
            },
            "compliance_checker": {
                "contract_text": contract_text,
                "contract_type": contract_type,
            },
            "report_generator": {
                "previous_results": task_context.get("all_previous_results", {}),
            },
        }

        return agent_inputs.get(agent_name, {
            "contract_text": contract_text,
            "contract_type": contract_type,
        })

    def _format_response(
        self,
        intent_type: IntentType,
        results: Dict[str, Any],
        ctx: ConversationContext,
    ) -> str:
        """
        根据意图类型和Agent结果生成用户友好的回复

        Args:
            intent_type: 意图类型
            results: Agent执行结果字典 {agent_name: result}
            ctx: 对话上下文

        Returns:
            格式化的回复文本
        """
        if not results:
            return "抱歉，处理过程中出现了问题。"

        # 完整合同审查
        if intent_type == IntentType.CONTRACT_REVIEW:
            completed_agents = [name for name, r in results.items() if r.get("status") == "completed"]
            failed_agents = [name for name, r in results.items() if r.get("status") == "error"]

            response = f"📋 合同审查完成\n\n"
            response += f"已完成: {len(completed_agents)} 个分析\n"

            if failed_agents:
                response += f"失败: {', '.join(failed_agents)}\n"

            response += "\n如需进一步分析，请告诉我具体需求，例如：\n"
            response += "- 评估风险\n"
            response += "- 分析条款\n"
            response += "- 检查合规性\n"
            response += "- 生成报告"
            return response

        # 风险评估
        if intent_type == IntentType.RISK_ASSESSMENT:
            if "risk_assessor" in results and results["risk_assessor"].get("status") == "completed":
                risk_result = results["risk_assessor"].get("result", {})
                risk_level = risk_result.get("risk_level", "unknown")
                risks = risk_result.get("risks", [])
                level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")
                response = f"⚠️ 风险评估完成 {level_emoji}\n\n"
                response += f"风险等级: {risk_level.upper()}\n\n"
                for i, risk in enumerate(risks, 1):
                    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity"), "⚪")
                    response += f"{i}. {emoji} {risk.get('name', '无描述')}\n"
                response += "\n如需详细分析某个风险点，请告诉我。"
                return response

        # 条款分析
        if intent_type == IntentType.CLAUSE_ANALYSIS:
            if "clause_analyst" in results and results["clause_analyst"].get("status") == "completed":
                clause_result = results["clause_analyst"].get("result", {})
                issues = clause_result.get("issues_found", 0)
                response = f"📋 条款分析完成\n\n"
                response += f"发现问题: {issues} 个\n\n"
                return response

        # 合规检查
        if intent_type == IntentType.COMPLIANCE_CHECK:
            if "compliance_checker" in results and results["compliance_checker"].get("status") == "completed":
                compliance_result = results["compliance_checker"].get("result", {})
                score = compliance_result.get("score", 0)
                violations = compliance_result.get("compliance_violations", [])
                response = f"✅ 合规检查完成\n\n"
                response += f"合规评分: {score}/100\n\n"
                if violations:
                    response += "需要改进:\n"
                    for violation in violations:
                        response += f"- ⚠️ {violation.get('suggestion', '无')}\n"
                else:
                    response += "未发现合规问题。\n"
                return response

        # 报告生成
        if intent_type == IntentType.REPORT_GENERATION:
            if "report_generator" in results and results["report_generator"].get("status") == "completed":
                report_result = results["report_generator"].get("result", {})
                report = report_result.get("report", {})
                response = f"📊 审查报告已生成\n\n"
                response += f"报告标题: {report.get('title', '合同审查报告')}\n"
                response += f"生成时间: {report_result.get('generated_at', '未知')}\n"
                return response

        # 问题回答
        if intent_type == IntentType.QUESTION_ANSWER:
            if "question_answerer" in results and results["question_answerer"].get("status") == "completed":
                return results["question_answerer"].get("result", {}).get("answer", "让我为您解答这个问题。")

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
