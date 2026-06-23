"""
多轮对话处理器 - 弱中心化调度器（启动协调者）

阶段1改造后职责：
- 意图识别（不变）
- 初始化共享内存 + 消息总线
- 发布 task.created 事件启动事件链
- 等待 task.completed 事件返回结果（asyncio.Event + 全局超时）
- 聚合栅栏：共享内存计数器，所有分析完成后自动触发报告生成
- 问候/追问/未知意图直接处理（不变）
- 异常兜底：超时熔断、Agent 失败降级
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .intent_recognizer import IntentRecognizer, IntentType, Intent
from .conversation_context import ConversationContext, ConversationManager, ConversationState
from .communication import AgentMessage, MessageType, MessageBus
from .business_events import BusinessEvent
from src.memory.shared_memory import SharedMemoryManager
from src.memory.memory_layer import MemoryLayer
from src.utils.llm_factory import get_llm

logger = logging.getLogger(__name__)

# 全局超时：每个任务最大执行时长（秒）
_TASK_TIMEOUT = 180

# 意图到所需 Agent 的映射
INTENT_REQUIRED_AGENTS = {
    IntentType.CONTRACT_REVIEW: ["document_parser", "risk_assessor", "clause_analyst", "compliance_checker", "report_generator"],
    IntentType.RISK_ASSESSMENT: ["risk_assessor"],
    IntentType.CLAUSE_ANALYSIS: ["clause_analyst"],
    IntentType.COMPLIANCE_CHECK: ["compliance_checker"],
    IntentType.REPORT_GENERATION: ["report_generator"],
}


class MultiTurnHandler:
    """
    多轮对话处理器（弱中心化 — 启动协调者）

    核心职责：
    1. 意图识别
    2. 初始化共享内存和消息总线
    3. 启动事件驱动的 Agent 协作链
    4. 等待最终结果并返回（asyncio.Event + 超时熔断）
    """

    def __init__(
        self,
        intent_recognizer: Optional[IntentRecognizer] = None,
        conversation_manager: Optional[ConversationManager] = None,
    ):
        self.intent_recognizer = intent_recognizer or IntentRecognizer()
        self.conversation_manager = conversation_manager or ConversationManager()
        self._agents: Dict[str, BaseAgent] = {}

        # 阶段1：事件驱动基础设施
        self._shared_memory: Optional[SharedMemoryManager] = None
        self._message_bus: Optional[MessageBus] = None
        self._completion_event: Optional[asyncio.Event] = None
        self._analysis_complete_event: Optional[asyncio.Event] = None

        logger.info("多轮对话处理器初始化（弱中心化模式）")

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

        对外接口不变，内部改为事件驱动。
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

        # 5. 构建任务上下文（用于追问等直接回复场景）
        task_context = ctx.build_task_context()
        task_context["intent"] = intent.to_dict()
        task_context["user_message"] = user_message

        # 6. 注入追问上下文
        task_context = self._inject_follow_up_context(task_context, intent, ctx)

        # 7. 处理问候、未知意图和问题回答（不需要Agent）
        if intent.type in (IntentType.GREETING, IntentType.QUESTION_ANSWER, IntentType.UNKNOWN):
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

        # 8. 需要 Agent 执行的意图 → 事件驱动模式
        # 检查是否需要合同文本
        requires_contract = intent.type in (
            IntentType.CONTRACT_REVIEW, IntentType.RISK_ASSESSMENT,
            IntentType.CLAUSE_ANALYSIS, IntentType.COMPLIANCE_CHECK,
        )
        if requires_contract and not contract_text and not ctx.get_contract_text():
            response = "请先上传或提供合同文本，然后我再帮您进行分析。"
            ctx.add_assistant_message(response)
            return {
                "session_id": session_id,
                "intent": intent.to_dict(),
                "agents": [],
                "result": None,
                "response": response,
                "needs_contract": True,
            }

        # 9. 初始化事件驱动基础设施
        effective_contract = contract_text or ctx.get_contract_text() or ""
        self._init_infrastructure(session_id, effective_contract, intent, file_info)

        # 10. 绑定基础设施到所有 Agent（传入聚合屏障回调）
        for agent in self._agents.values():
            agent.bind_infrastructure(
                self._shared_memory,
                self._message_bus,
                on_all_complete=self._on_all_analyses_complete,
            )

        # 11. 执行事件驱动的 Agent 协作链
        result = await self._execute_event_driven(intent.type, session_id)

        # 12. 从共享内存收集结果，存入上下文
        all_results = self._collect_results()
        for agent_name, agent_result in all_results.items():
            ctx.set_agent_result(agent_name, agent_result)

        # 13. 生成回复
        response = self._format_response(intent.type, all_results, ctx)
        ctx.add_assistant_message(response)

        return {
            "session_id": session_id,
            "intent": intent.to_dict(),
            "agents": list(all_results.keys()),
            "result": result,
            "response": response,
            "context_summary": self._get_context_summary(ctx),
        }

    # ==================== 事件驱动执行 ====================

    def _on_all_analyses_complete(self):
        """聚合屏障回调：所有分析 Agent 完成后由最后一个 Agent 调用"""
        logger.info("聚合屏障归零：所有分析 Agent 已完成")
        if self._analysis_complete_event:
            self._analysis_complete_event.set()

    def _init_infrastructure(
        self,
        session_id: str,
        contract_text: str,
        intent: Intent,
        file_info: Optional[Dict[str, Any]] = None,
    ):
        """初始化共享内存和消息总线，写入 CONTEXT 层原始数据"""
        # 创建本次会话的共享内存
        self._shared_memory = SharedMemoryManager(contract_id=session_id)
        self._message_bus = MessageBus()
        self._completion_event = asyncio.Event()
        self._analysis_complete_event = asyncio.Event()

        # 写入 CONTEXT 层（原始输入，写入一次后只读）
        contract_type = "general"
        if file_info:
            contract_type = file_info.get("contract_type", "general")

        self._shared_memory.write("coordinator", "contract_text", contract_text, MemoryLayer.CONTEXT)
        self._shared_memory.write("coordinator", "contract_type", contract_type, MemoryLayer.CONTEXT)
        self._shared_memory.write("coordinator", "intent_type", intent.type.value, MemoryLayer.CONTEXT)
        self._shared_memory.write("coordinator", "session_id", session_id, MemoryLayer.CONTEXT)

        # 聚合栅栏：待完成分析 Agent 计数器
        required = INTENT_REQUIRED_AGENTS.get(intent.type, [])
        analysis_agents = [a for a in ["risk_assessor", "clause_analyst", "compliance_checker"] if a in required]
        self._shared_memory.write(
            "coordinator", "_pending_count", len(analysis_agents), MemoryLayer.CONTEXT,
            validate=False,  # 内部字段，跳过 Schema 校验
        )
        self._shared_memory.write(
            "coordinator", "_required_agents", required, MemoryLayer.CONTEXT,
            validate=False,
        )

        logger.info(
            f"共享内存初始化完成: session={session_id}, "
            f"pending_analyses={len(analysis_agents)}, required={required}"
        )

    async def _execute_event_driven(self, intent_type: IntentType, session_id: str) -> Dict[str, Any]:
        """
        执行事件驱动的 Agent 协作链（带全局超时熔断）

        根据意图类型选择不同的执行路径：
        - CONTRACT_REVIEW: 完整链路（聚合栅栏驱动）
        - 单 Agent 意图: 按需执行
        """
        task = {"session_id": session_id}

        try:
            result = await asyncio.wait_for(
                self._execute_by_intent(intent_type, task),
                timeout=_TASK_TIMEOUT,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(f"任务执行超时（{_TASK_TIMEOUT}s），熔断终止")
            return {"error": f"执行超时（{_TASK_TIMEOUT}秒）", "status": "timeout"}
        except Exception as e:
            logger.error(f"事件驱动执行失败: {e}", exc_info=True)
            return {"error": str(e), "status": "error"}

    async def _execute_by_intent(self, intent_type: IntentType, task: Dict[str, Any]) -> Dict[str, Any]:
        """根据意图类型分发执行"""
        if intent_type == IntentType.CONTRACT_REVIEW:
            return await self._execute_full_review_chain(task)

        elif intent_type in (IntentType.RISK_ASSESSMENT, IntentType.CLAUSE_ANALYSIS,
                             IntentType.COMPLIANCE_CHECK, IntentType.REPORT_GENERATION):
            agent_map = {
                IntentType.RISK_ASSESSMENT: "risk_assessor",
                IntentType.CLAUSE_ANALYSIS: "clause_analyst",
                IntentType.COMPLIANCE_CHECK: "compliance_checker",
                IntentType.REPORT_GENERATION: "report_generator",
            }
            agent_name = agent_map[intent_type]
            result = await self._execute_single_agent(agent_name, task)
            # 单 Agent 场景：设置所有事件（分析完成 + 任务完成）
            self._analysis_complete_event.set()
            self._completion_event.set()
            return result

        else:
            logger.warning(f"未知意图类型: {intent_type}")
            return {}

    async def _execute_full_review_chain(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        完整审查链路（聚合栅栏驱动）

        链路：
        1. DocumentParser 执行 → 发布 document.parsed
        2. Risk + Clause + Compliance 并行执行（按需，只执行 required_agents 中的）
        3. 聚合栅栏：每个分析 Agent 完成后计数器 -1，归零时触发 ReportGenerator
        4. 等待 task.completed 事件
        """
        required = self._shared_memory.read("coordinator", "_required_agents", MemoryLayer.CONTEXT) or []

        # Step 1: 文档解析（如果在 required 列表中）
        if "document_parser" in required:
            logger.info("Step 1: 文档解析")
            parse_result = await self._execute_single_agent("document_parser", task)
            if isinstance(parse_result, dict) and "error" in parse_result:
                logger.warning(f"文档解析失败，跳过后续步骤: {parse_result}")
                self._completion_event.set()
                return parse_result

        # Step 2: 按需并行执行分析 Agent（只执行 required 列表中的）
        # Agent 完成后会递减 _pending_count，归零时设置 _analysis_complete_event
        analysis_tasks = []
        analysis_names = []
        for agent_name in ["risk_assessor", "clause_analyst", "compliance_checker"]:
            if agent_name in required:
                analysis_tasks.append(self._execute_single_agent(agent_name, task))
                analysis_names.append(agent_name)

        if analysis_tasks:
            logger.info(f"Step 2: 并行执行 {analysis_names}（等待聚合屏障归零）")

            # 启动所有分析 Agent，但不等待完成
            # Agent 完成后会通过 decrement_pending_count() 递减计数器
            gather_task = asyncio.create_task(
                asyncio.gather(*analysis_tasks, return_exceptions=True)
            )

            # 等待聚合屏障归零（所有分析 Agent 完成）
            try:
                await asyncio.wait_for(
                    self._analysis_complete_event.wait(),
                    timeout=_TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(f"聚合屏障等待超时（{_TASK_TIMEOUT}s）")
                gather_task.cancel()

            # 处理异常（降级）
            if gather_task.done() and not gather_task.cancelled():
                analysis_results = gather_task.result()
                for agent_name, result in zip(analysis_names, analysis_results):
                    if isinstance(result, Exception):
                        logger.error(f"Agent {agent_name} 执行异常: {result}，标记为失败")
                        self._shared_memory.write(
                            "coordinator", f"{agent_name}_status", "failed", MemoryLayer.ANALYSIS,
                            validate=False,
                        )

        # Step 3: ReportGenerator 已被最后一个分析 Agent 自动触发
        # 等待 ReportGenerator 完成（通过 _completion_event）
        if "report_generator" in required:
            logger.info("Step 3: 等待 ReportGenerator 完成")
            try:
                await asyncio.wait_for(
                    self._completion_event.wait(),
                    timeout=_TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(f"ReportGenerator 等待超时（{_TASK_TIMEOUT}s）")

        # 汇总所有结果
        all_results = self._collect_results()
        if "document_parser" in required:
            all_results["document_parser"] = parse_result

        return all_results

    async def _execute_single_agent(self, agent_name: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个 Agent（全链路容错）

        容错设计：
        - 无论成功失败，都必须完成状态重置
        - Agent 异常不向上抛出，降级为错误结果
        """
        if agent_name not in self._agents:
            logger.warning(f"Agent 未注册: {agent_name}")
            return {"status": "skipped", "reason": "agent_not_registered"}

        agent = self._agents[agent_name]
        try:
            agent.set_running(True)
            logger.info(f"开始执行 Agent: {agent_name}")
            result = await agent.process(task)
            logger.info(f"Agent 执行完成: {agent_name}")
            return result
        except Exception as e:
            logger.error(f"Agent 执行失败: {agent_name} - {e}", exc_info=True)
            # 降级：返回错误结果，不中断链路
            return {"status": "error", "agent": agent_name, "error": str(e)}
        finally:
            agent.set_running(False)

    def _collect_results(self) -> Dict[str, Any]:
        """从共享内存收集所有 ANALYSIS 层结果"""
        if self._shared_memory is None:
            return {}

        results = {}
        analysis_keys = self._shared_memory.get_all_keys(MemoryLayer.ANALYSIS)
        for key in analysis_keys:
            value = self._shared_memory.read("collector", key, MemoryLayer.ANALYSIS)
            if value is not None:
                results[key] = value

        # 也收集 DECISION 层
        decision_keys = self._shared_memory.get_all_keys(MemoryLayer.DECISION)
        for key in decision_keys:
            value = self._shared_memory.read("collector", key, MemoryLayer.DECISION)
            if value is not None:
                results[key] = value

        return results

    # ==================== 保留方法（不变） ====================

    def _get_direct_response(self, intent_type: IntentType) -> str:
        """获取问候和未知意图的直接回复"""
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
        return (
            "抱歉，我不太理解您的意思。您可以：\n\n"
            "- 上传合同文本进行审查\n"
            "- 告诉我具体需求（如：评估风险、分析条款）\n"
            "- 问我关于合同的问题"
        )

    async def _answer_from_context(self, user_message: str, ctx: ConversationContext) -> str:
        """基于上下文回答用户问题（使用LLM理解对话历史）"""
        logger.info(f"追问处理: message={user_message[:50]}, session={ctx.session_id}")

        messages = ctx.get_messages()
        logger.info(f"上下文消息数: {len(messages)}")
        if not messages:
            return "目前还没有进行过对话。请先上传合同文件，然后我可以帮你分析。"

        context_parts = []

        contract_text = ctx.get_contract_text()
        if contract_text:
            context_parts.append(f"=== 合同内容 ===\n{contract_text[:3000]}")
            logger.info(f"合同内容: {len(contract_text)}字")
        else:
            logger.warning("未找到合同内容")

        context_parts.append("\n=== 对话历史 ===")
        for msg in messages:
            role = "用户" if msg["role"] == "user" else "助手"
            context_parts.append(f"{role}: {msg['content'][:500]}")

        context_str = "\n".join(context_parts)

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm()
            llm_messages = [
                SystemMessage(content="""你是一个合同审查助手。用户之前已经对合同进行了分析，现在在追问细节。

规则：
1. 根据提供的合同内容和对话历史回答用户问题
2. 对话历史中助手的回复包含了之前的分析结果，直接引用即可
3. 回答要简洁明了，直接回答问题
4. 如果上下文中没有相关信息，如实告知"""),
                HumanMessage(content=f"""{context_str}

用户问题：{user_message}""")
            ]

            response = await llm.ainvoke(llm_messages)
            content = response.content
            if isinstance(content, list):
                text_parts = [block.get("text", "") for block in content
                              if isinstance(block, dict) and block.get("type") == "text"]
                content = "\n".join(text_parts) if text_parts else str(content)
            logger.info(f"LLM回答完成: {len(content)}字")
            return content

        except Exception as e:
            logger.error(f"LLM回答失败: {e}", exc_info=True)
            return "抱歉，回答问题时出现错误。您可以尝试重新提问。"

    def _inject_follow_up_context(
        self,
        task_context: Dict[str, Any],
        intent: Intent,
        ctx: ConversationContext,
    ) -> Dict[str, Any]:
        """注入追问上下文"""
        all_results = ctx.get_all_results()

        if not all_results:
            return task_context

        if intent.type == IntentType.RISK_ASSESSMENT:
            if "document_parser" in all_results:
                task_context["parsed_result"] = all_results["document_parser"]

        if intent.type == IntentType.CLAUSE_ANALYSIS:
            if "risk_assessor" in all_results:
                task_context["risk_result"] = all_results["risk_assessor"]

        if intent.type == IntentType.REPORT_GENERATION:
            task_context["all_previous_results"] = all_results

        return task_context

    def _format_response(
        self,
        intent_type: IntentType,
        results: Dict[str, Any],
        ctx: ConversationContext,
    ) -> str:
        """根据意图类型和Agent结果生成用户友好的回复"""
        if not results:
            return "抱歉，处理过程中出现了问题。"

        if intent_type == IntentType.CONTRACT_REVIEW:
            completed = [name for name, r in results.items()
                        if isinstance(r, dict) and r.get("status") != "error"]
            failed = [name for name, r in results.items()
                     if isinstance(r, dict) and r.get("status") == "error"]

            response = f"📋 合同审查完成\n\n"
            response += f"已完成: {len(completed)} 个分析\n"
            if failed:
                response += f"失败: {', '.join(failed)}\n"
            response += "\n如需进一步分析，请告诉我具体需求。"
            return response

        if intent_type == IntentType.RISK_ASSESSMENT:
            risk_result = results.get("risk_assessor", {})
            if isinstance(risk_result, dict) and "risk_level" in risk_result:
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

        if intent_type == IntentType.CLAUSE_ANALYSIS:
            clause_result = results.get("clause_analyst", {})
            if isinstance(clause_result, dict):
                issues = clause_result.get("issues_found", 0)
                return f"📋 条款分析完成\n\n发现问题: {issues} 个\n\n如需详细分析，请告诉我。"

        if intent_type == IntentType.COMPLIANCE_CHECK:
            compliance_result = results.get("compliance_checker", {})
            if isinstance(compliance_result, dict):
                score = compliance_result.get("score", 0)
                violations = compliance_result.get("compliance_violations", [])
                response = f"✅ 合规检查完成\n\n合规评分: {score}/100\n\n"
                if violations:
                    response += "需要改进:\n"
                    for v in violations:
                        response += f"- ⚠️ {v.get('suggestion', '无')}\n"
                else:
                    response += "未发现合规问题。\n"
                return response

        if intent_type == IntentType.REPORT_GENERATION:
            report_result = results.get("report_generator", {})
            if isinstance(report_result, dict):
                report = report_result.get("report", {})
                return f"📊 审查报告已生成\n\n报告标题: {report.get('title', '合同审查报告')}\n"

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
        """获取支持的意图信息"""
        return [
            {"intent": "contract_review", "description": "完整合同审查", "requires_contract": True},
            {"intent": "risk_assessment", "description": "风险评估", "requires_contract": True},
            {"intent": "clause_analysis", "description": "条款分析", "requires_contract": True},
            {"intent": "compliance_check", "description": "合规检查", "requires_contract": True},
            {"intent": "report_generation", "description": "报告生成", "requires_contract": False},
            {"intent": "question_answer", "description": "问题回答", "requires_contract": False},
            {"intent": "greeting", "description": "问候", "requires_contract": False},
        ]
