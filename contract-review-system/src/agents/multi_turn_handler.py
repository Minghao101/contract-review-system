"""
多轮对话处理器 - 完全事件驱动调度器（启动协调者）

职责：
- 意图识别（不变）
- 初始化共享内存 + 消息总线
- 发布 task.created 事件启动事件链（Agent 自主订阅和协作）
- 等待 task.completed 事件返回结果（asyncio.Event + 全局超时）
- 问候/追问/未知意图直接处理（不变）
- 异常兜底：超时熔断、Agent 失败降级
"""
import asyncio
import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

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

# 会话级上下文变量（并发隔离：每个请求有独立的 session_id）
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    'current_session_id', default='default'
)


@dataclass
class TaskRuntime:
    """单次请求的运行时上下文（解决并发隔离问题）"""
    session_id: str
    shared_memory: SharedMemoryManager
    message_bus: MessageBus
    completion_event: asyncio.Event
    analysis_complete_event: asyncio.Event


class RuntimeProxy:
    """
    运行时代理 - 解决 Agent Singleton 绑定问题

    Agent 的 bind_infrastructure() 绑定此 proxy 而非具体 SharedMemoryManager。
    proxy 在 read/write 时通过 contextvars 自动解析到当前 session 的 runtime，
    实现请求级隔离，无需修改 Agent 的 process() 签名。
    """

    def __init__(self, get_runtime_fn: Callable[[str], Optional[TaskRuntime]]):
        self._get_runtime = get_runtime_fn

    def _get_sm(self) -> Optional[SharedMemoryManager]:
        session_id = _current_session_id.get()
        runtime = self._get_runtime(session_id)
        return runtime.shared_memory if runtime else None

    def read(self, agent_id: str, key: str, layer: MemoryLayer) -> Optional[Any]:
        sm = self._get_sm()
        return sm.read(agent_id, key, layer) if sm else None

    def write(self, agent_id: str, key: str, value: Any, layer: MemoryLayer, validate: bool = True) -> int:
        sm = self._get_sm()
        return sm.write(agent_id, key, value, layer, validate=validate) if sm else 0

    def get_all_keys(self, layer: MemoryLayer) -> List[str]:
        sm = self._get_sm()
        return sm.get_all_keys(layer) if sm else []

    def subscribe(self, key: str, callback: Callable):
        sm = self._get_sm()
        if sm:
            sm.subscribe(key, callback)

    def unsubscribe(self, key: str, callback: Callable):
        sm = self._get_sm()
        if sm:
            sm.unsubscribe(key, callback)


class MessageBusProxy:
    """
    消息总线代理 - 同 RuntimeProxy 原理

    Agent 的 bind_infrastructure() 绑定此 proxy 而非具体 MessageBus。
    """

    def __init__(self, get_runtime_fn: Callable[[str], Optional[TaskRuntime]]):
        self._get_runtime = get_runtime_fn

    def _get_bus(self) -> Optional[MessageBus]:
        session_id = _current_session_id.get()
        runtime = self._get_runtime(session_id)
        return runtime.message_bus if runtime else None

    def publish(self, message):
        bus = self._get_bus()
        if bus:
            bus.publish(message)


# 意图到所需 Agent 的映射
INTENT_REQUIRED_AGENTS = {
    IntentType.CONTRACT_REVIEW: ["document_parser", "risk_assessor", "clause_analyst", "compliance_checker", "report_generator"],
    IntentType.RISK_ASSESSMENT: ["risk_assessor"],
    IntentType.CLAUSE_ANALYSIS: ["clause_analyst"],
    IntentType.COMPLIANCE_CHECK: ["compliance_checker"],
    IntentType.REPORT_GENERATION: ["report_generator"],
    IntentType.MODIFY_CONTRACT: ["document_parser", "risk_assessor", "clause_analyst", "compliance_checker"],
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

        # 会话级运行时（解决并发隔离问题）
        self._runtimes: Dict[str, TaskRuntime] = {}

        # RuntimeProxy / MessageBusProxy：Agent 绑定 proxy 而非具体实例
        # proxy 通过 contextvars 在 read/write 时自动解析到当前 session 的 runtime
        self._sm_proxy = RuntimeProxy(lambda sid: self._runtimes.get(sid))
        self._bus_proxy = MessageBusProxy(lambda sid: self._runtimes.get(sid))

        logger.info("多轮对话处理器初始化（完全事件驱动模式）")

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
                # 优先从 SharedMemory CONTEXT 读取修改后的 contract_text
                effective_contract = contract_text or ctx.get_contract_text() or ""
                # 检查是否有已存在的 runtime（之前修改过合同）
                existing_runtime = self._runtimes.get(session_id)
                if existing_runtime:
                    sm_contract = existing_runtime.shared_memory.read(
                        "coordinator", "contract_text", MemoryLayer.CONTEXT
                    )
                    if sm_contract:
                        effective_contract = sm_contract
                        logger.info(f"追问: 从 SharedMemory 读取修改后的合同文本（{len(sm_contract)}字）")
                    else:
                        logger.warning(f"追问: SharedMemory 中无 contract_text")
                else:
                    logger.warning(f"追问: 未找到已有 runtime, session={session_id}")
                response = await self._answer_from_context(user_message, ctx, effective_contract)
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
            IntentType.MODIFY_CONTRACT,
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

        # 9. 初始化事件驱动基础设施（每次请求独立运行时）
        effective_contract = contract_text or ctx.get_contract_text() or ""
        runtime = self._init_runtime(session_id, effective_contract, intent, file_info)

        # 9.1 设置 session 上下文变量（proxy 通过此变量路由到正确的 runtime）
        token = _current_session_id.set(session_id)

        # 9.2 存储用户原始消息（供修改指令解析使用）
        runtime.shared_memory.write("coordinator", "user_message", user_message, MemoryLayer.CONTEXT, validate=False)

        # 10. 绑定 proxy 到所有 Agent（而非具体 SharedMemoryManager，解决 singleton 并发问题）
        #     Agent 会自动订阅各自关心的事件
        for agent in self._agents.values():
            agent.bind_infrastructure(self._sm_proxy, self._bus_proxy)

        # 10.1 订阅 task.completed 事件（ReportGenerator 完成后设置 completion_event）
        def _on_task_completed(message):
            logger.info("收到 task.completed 事件，设置 completion_event")
            runtime.completion_event.set()
        runtime.message_bus.subscribe_event(BusinessEvent.TASK_COMPLETED, _on_task_completed)

        # 11. 执行事件驱动的 Agent 协作链
        result = await self._execute_event_driven(runtime, intent.type)

        # 12. 从共享内存收集结果，存入上下文
        all_results = self._collect_results(runtime)
        for agent_name, agent_result in all_results.items():
            ctx.set_agent_result(agent_name, agent_result)

        # 13. 生成回复
        response = self._format_response(intent.type, all_results, ctx)

        # 14. 释放 session 上下文（runtime 保留在 _runtimes 中，供下次请求复用）
        _current_session_id.reset(token)
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

    def _init_runtime(
        self,
        session_id: str,
        contract_text: str,
        intent: Intent,
        file_info: Optional[Dict[str, Any]] = None,
    ) -> TaskRuntime:
        """
        初始化单次请求的运行时上下文

        同一 session 复用已有的 SharedMemoryManager（保留之前的 ANALYSIS 数据），
        这样增量修改可以读到之前的解析结果。
        """
        # 复用已有 runtime（保留 ANALYSIS 数据，实现增量修改）
        existing_runtime = self._runtimes.get(session_id)
        if existing_runtime:
            shared_memory = existing_runtime.shared_memory
            logger.info(f"复用已有 runtime: session={session_id}，保留 ANALYSIS 数据")
        else:
            shared_memory = SharedMemoryManager(contract_id=session_id)

        message_bus = MessageBus()
        completion_event = asyncio.Event()
        analysis_complete_event = asyncio.Event()

        # 更新 CONTEXT 层（意图类型每次请求可能不同）
        contract_type = "general"
        if file_info:
            contract_type = file_info.get("contract_type", "general")

        shared_memory.write("coordinator", "contract_text", contract_text, MemoryLayer.CONTEXT)
        shared_memory.write("coordinator", "contract_type", contract_type, MemoryLayer.CONTEXT)
        shared_memory.write("coordinator", "intent_type", intent.type.value, MemoryLayer.CONTEXT)
        shared_memory.write("coordinator", "session_id", session_id, MemoryLayer.CONTEXT)

        # 记录所需 Agent（供按需调度使用）
        required = INTENT_REQUIRED_AGENTS.get(intent.type, [])
        shared_memory.write("coordinator", "_required_agents", required, MemoryLayer.CONTEXT, validate=False)

        runtime = TaskRuntime(
            session_id=session_id,
            shared_memory=shared_memory,
            message_bus=message_bus,
            completion_event=completion_event,
            analysis_complete_event=analysis_complete_event,
        )
        self._runtimes[session_id] = runtime

        logger.info(
            f"运行时初始化完成: session={session_id}, "
            f"intent={intent.type.value}, required={required}"
        )
        return runtime

    async def _execute_event_driven(self, runtime: TaskRuntime, intent_type: IntentType) -> Dict[str, Any]:
        """
        执行事件驱动的 Agent 协作链（带全局超时熔断）

        完全事件驱动：调度器只发布事件，Agent 自主订阅和协作。
        """
        task = {"session_id": runtime.session_id}

        # 增量修改流程保持手动编排（复杂场景暂不改造）
        if intent_type == IntentType.MODIFY_CONTRACT:
            return await self._execute_incremental_modify(runtime, task)

        # 单 Agent 意图：直接调用特定 Agent（不走完整事件链）
        single_agent_map = {
            IntentType.RISK_ASSESSMENT: "risk_assessor",
            IntentType.CLAUSE_ANALYSIS: "clause_analyst",
            IntentType.COMPLIANCE_CHECK: "compliance_checker",
            IntentType.REPORT_GENERATION: "report_generator",
        }
        if intent_type in single_agent_map:
            agent_name = single_agent_map[intent_type]
            result = await self._execute_single_agent(agent_name, task)
            runtime.completion_event.set()
            return result

        try:
            # 发布初始事件，Agent 自动订阅和协作
            self._publish_event(runtime, BusinessEvent.TASK_CREATED, {
                "session_id": runtime.session_id,
            })
            logger.info(f"已发布事件: {BusinessEvent.TASK_CREATED}")

            # 等待 task.completed 事件（ReportGenerator 完成后发布）
            await asyncio.wait_for(
                runtime.completion_event.wait(),
                timeout=_TASK_TIMEOUT,
            )
            return {"status": "completed"}

        except asyncio.TimeoutError:
            logger.error(f"任务执行超时（{_TASK_TIMEOUT}s），熔断终止")
            return {"error": f"执行超时（{_TASK_TIMEOUT}秒）", "status": "timeout"}
        except Exception as e:
            logger.error(f"事件驱动执行失败: {e}", exc_info=True)
            return {"error": str(e), "status": "error"}

    def _publish_event(self, runtime: TaskRuntime, event_type: str, data: Dict[str, Any] = None):
        """发布事件到当前运行时的消息总线"""
        from .communication import AgentMessage, MessageType
        content = {"event": event_type}
        if data:
            content.update(data)
        msg = AgentMessage(
            sender_id="coordinator",
            receiver_id="*",
            message_type=MessageType.NOTIFICATION,
            content=content,
        )
        runtime.message_bus.publish(msg)

    async def _execute_incremental_modify(self, runtime: TaskRuntime, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        增量修改流程（不使用聚合栅栏，直接 await 所有分析任务）

        1. LLM 解析修改指令
        2. DocumentParser 定位并替换条款
        3. 各分析 Agent 单条款增量分析
        """
        # Step 1: LLM 解析修改指令
        user_message = runtime.shared_memory.read("coordinator", "user_message", MemoryLayer.CONTEXT) or ""
        instruction = await self._parse_modify_instruction(user_message)

        if not instruction:
            return {"error": "无法理解修改意图，请更具体地描述"}

        confidence = instruction.get("confidence", 0)
        if confidence < 0.5:
            return {"error": f"修改意图不够明确（置信度 {confidence:.0%}），请更具体地描述，例如'把第三条的违约金从5%改成3%'"}

        runtime.shared_memory.write(
            "coordinator", "modify_instruction", instruction, MemoryLayer.ANALYSIS,
            validate=False,
        )
        logger.info(f"修改指令解析: {instruction}")

        # Step 2: DocumentParser 定位并替换条款
        parse_result = await self._execute_single_agent("document_parser", task)
        if isinstance(parse_result, dict) and "error" in parse_result:
            logger.warning(f"条款定位失败: {parse_result}")
            return parse_result

        # Step 3: 单条款增量分析（直接 await，不走聚合栅栏）
        analysis_tasks = []
        analysis_names = []
        for agent_name in ["risk_assessor", "clause_analyst", "compliance_checker"]:
            if agent_name in self._agents:
                analysis_tasks.append(self._execute_single_agent(agent_name, task))
                analysis_names.append(agent_name)

        if analysis_tasks:
            logger.info(f"增量分析: {analysis_names}")
            await asyncio.gather(*analysis_tasks, return_exceptions=True)

        # 汇总结果
        all_results = self._collect_results(runtime)
        all_results["document_parser"] = parse_result
        return all_results

    async def _parse_modify_instruction(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 从用户消息中提取修改指令

        Args:
            user_message: 用户原始消息

        Returns:
            修改指令字典，解析失败返回 None
        """
        if not user_message:
            return None

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from src.agents.shared_data_schemas import ModifyInstruction

            system_prompt = """你是一个合同修改指令解析器。从用户输入中提取修改指令。

输出格式要求（必须是严格有效的JSON）：
{
  "action": "replace/delete/insert",
  "locate_type": "clause_number/clause_title/semantic",
  "locate_value": "第三条/违约责任/关于付款的条款",
  "old_content": "被替换的原文（replace时必填）",
  "new_content": "新内容（replace/insert时必填）",
  "target_scope": "single_clause",
  "confidence": 0.8
}

规则：
1. locate_value 用用户原文中的表述
2. 如果用户说"第三条"，locate_type="clause_number"，locate_value="第三条"
3. 如果用户说"违约责任那条"，locate_type="clause_title"，locate_value="违约责任"
4. 如果用户说"关于付款的条款"，locate_type="semantic"，locate_value="关于付款的条款"
5. confidence 根据表述清晰度打分（0.5-1.0）
6. replace 时尽量提取 old_content（用户说的原文片段）
7. "加上"、"添加"、"增加"、"补充"、"加入" → action="insert"
8. insert 时 locate_value 描述要添加的条款类型（如"责任限制"），new_content 包含用户要求的具体内容
9. 只输出JSON"""

            llm = get_llm()
            structured_llm = llm.with_structured_output(ModifyInstruction)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"用户修改指令：{user_message}"),
            ]

            result = await structured_llm.ainvoke(messages)

            if isinstance(result, ModifyInstruction):
                return result.model_dump()
            elif isinstance(result, dict):
                return result

        except Exception as e:
            logger.error(f"修改指令解析失败: {e}")

        return None

    async def _execute_single_agent(self, agent_name: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个 Agent（全链路容错）

        容错设计：
        - Agent 异常不向上抛出，降级为错误结果
        - 状态管理（set_running）和计数器（decrement_pending_count）由 Agent.process() 自行负责
        """
        if agent_name not in self._agents:
            logger.warning(f"Agent 未注册: {agent_name}")
            return {"status": "skipped", "reason": "agent_not_registered"}

        agent = self._agents[agent_name]
        try:
            logger.info(f"开始执行 Agent: {agent_name}")
            result = await agent.process(task)
            logger.info(f"Agent 执行完成: {agent_name}")
            return result
        except Exception as e:
            logger.error(f"Agent 执行失败: {agent_name} - {e}", exc_info=True)
            # 降级：返回错误结果，不中断链路
            return {"status": "error", "agent": agent_name, "error": str(e)}

    def _collect_results(self, runtime: TaskRuntime) -> Dict[str, Any]:
        """从运行时共享内存收集所有 ANALYSIS + DECISION 层结果"""
        results = {}
        for key in runtime.shared_memory.get_all_keys(MemoryLayer.ANALYSIS):
            value = runtime.shared_memory.read("collector", key, MemoryLayer.ANALYSIS)
            if value is not None:
                results[key] = value

        for key in runtime.shared_memory.get_all_keys(MemoryLayer.DECISION):
            value = runtime.shared_memory.read("collector", key, MemoryLayer.DECISION)
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

    async def _answer_from_context(
        self,
        user_message: str,
        ctx: ConversationContext,
        contract_text_override: Optional[str] = None,
    ) -> str:
        """基于上下文回答用户问题（使用LLM理解对话历史）"""
        logger.info(f"追问处理: message={user_message[:50]}, session={ctx.session_id}")

        messages = ctx.get_messages()
        logger.info(f"上下文消息数: {len(messages)}")
        if not messages:
            return "目前还没有进行过对话。请先上传合同文件，然后我可以帮你分析。"

        context_parts = []

        # 优先使用修改后的 contract_text，否则从 ConversationContext 读取
        contract_text = contract_text_override or ctx.get_contract_text()
        if contract_text:
            # 截断到合理长度（约 4000 token），避免丢失后部条款
            truncated = contract_text[:15000] if len(contract_text) > 15000 else contract_text
            context_parts.append(f"=== 合同内容 ===\n{truncated}")
            logger.info(f"合同内容: {len(contract_text)}字（发送{len(truncated)}字）")
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
1. 仔细阅读合同全文内容，找到与用户问题相关的条款
2. 对话历史中助手的回复包含了之前的分析结果，可直接引用
3. 如果合同中有明确条款回答用户问题，必须引用具体条款内容
4. 回答要简洁明了，直接回答问题
5. 只有在合同全文中确实找不到相关信息时才说"未发现"
6. 如果合同被修改过（如新增条款），修改后的内容在合同文本中可以找到"""),
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
            logger.info(f"LLM回答内容: {content[:300]}")
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

        if intent_type == IntentType.MODIFY_CONTRACT:
            doc_result = results.get("document_parser", {})
            risk_result = results.get("risk_assessor", {})
            clause_id = doc_result.get("updated_clause_id", "未知") if isinstance(doc_result, dict) else "未知"
            risk_level = risk_result.get("risk_level", "unknown") if isinstance(risk_result, dict) else "unknown"
            level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")

            response = f"✏️ 条款修改完成\n\n"
            response += f"已修改条款: {clause_id}\n"
            response += f"修改后风险等级: {risk_level.upper()} {level_emoji}\n"

            # 显示增量分析发现的问题
            if isinstance(risk_result, dict):
                risks = risk_result.get("risks", [])
                if risks:
                    response += f"\n修改后发现 {len(risks)} 个风险点:\n"
                    for i, risk in enumerate(risks[:3], 1):
                        emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity"), "⚪")
                        response += f"  {i}. {emoji} {risk.get('name', '无描述')}\n"

            response += "\n如需进一步调整，请告诉我。"
            return response

        if intent_type == IntentType.RISK_ASSESSMENT:
            risk_result = results.get("risk_assessor", {})
            if isinstance(risk_result, dict) and "risk_level" in risk_result:
                risk_level = risk_result.get("risk_level", "unknown")
                risks = risk_result.get("risks", [])
                level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")
                response = f"⚠️ 风险评估完成 {level_emoji}\n\n"
                response += f"风险等级: {risk_level.upper()}\n\n"

                # 风险列表（含描述和建议）
                for i, risk in enumerate(risks, 1):
                    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity"), "⚪")
                    response += f"{i}. {emoji} {risk.get('name', '无描述')}\n"
                    if risk.get("description"):
                        response += f"   {risk['description']}\n"
                    if risk.get("suggestion"):
                        response += f"   💡 建议: {risk['suggestion']}\n"

                # 风险量化
                quant = risk_result.get("risk_quantification", {})
                if quant:
                    response += f"\n📊 风险评分: {quant.get('risk_score', 0)}/100\n"
                    dist = quant.get("risk_distribution", {})
                    if any(dist.values()):
                        response += f"分布: 🔴高{dist.get('high', 0)} 🟡中{dist.get('medium', 0)} 🟢低{dist.get('low', 0)}\n"

                # 缓解建议
                mitigation = risk_result.get("mitigation_plan", [])
                if mitigation:
                    response += "\n🛡️ 缓解建议:\n"
                    for m in mitigation[:5]:
                        response += f"- {m.get('mitigation', '无')}\n"

                # 整体评估
                summary = risk_result.get("summary", {})
                if summary.get("overall_assessment"):
                    response += f"\n📝 {summary['overall_assessment']}\n"

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
            {"intent": "modify_contract", "description": "修改合同条款", "requires_contract": True},
            {"intent": "report_generation", "description": "报告生成", "requires_contract": False},
            {"intent": "question_answer", "description": "问题回答", "requires_contract": False},
            {"intent": "greeting", "description": "问候", "requires_contract": False},
        ]
