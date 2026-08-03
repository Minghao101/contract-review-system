"""
基础Agent模块 - 定义所有Agent的基类

增强功能（阶段1弱中心化）：
- bind_infrastructure(): 绑定共享内存和消息总线
- read_shared() / write_shared(): 读写共享内存
- publish_event(): 发布业务事件

LangChain 高级抽象：
- chat_structured(): 使用 with_structured_output() 返回 Pydantic 模型
- prompt_template: 子类定义 ChatPromptTemplate
- output_model: 子类定义输出 Pydantic 模型
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar
from datetime import datetime
import asyncio
import logging
from pydantic import BaseModel
from langchain_core.language_models import BaseLLM
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from src.utils.llm_factory import get_llm
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """
    Agent基类

    所有专业Agent都应继承此类并实现抽象方法

    LangChain 高级抽象支持：
    - prompt_template: ChatPromptTemplate 实例，子类在类级别定义
    - output_model: Pydantic 模型类，子类在类级别定义
    - chat_structured(): 自动格式化 prompt + structured output
    """

    # 子类覆盖：ChatPromptTemplate
    prompt_template: Optional[ChatPromptTemplate] = None
    # 子类覆盖：输出 Pydantic 模型
    output_model: Optional[Type[BaseModel]] = None

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        llm: Optional[BaseLLM] = None,
        description: str = "",
        tools: Optional[List] = None
    ):
        """
        初始化Agent

        Args:
            agent_id: Agent唯一标识符
            name: Agent名称
            role: Agent角色
            llm: LLM实例 (可选)
            description: Agent描述
            tools: 可用工具列表 (可选)
        """
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.description = description
        self.llm = llm or get_llm()

        # Agent状态
        self.is_running = False
        self.created_at = datetime.now()
        self.last_active_at = datetime.now()

        # 私有记忆（旧版兼容，新架构使用 AgentPrivateMemory）
        self.private_memory: Dict[str, Any] = {}

        # LangChain Agent包装器（延迟初始化）
        self._wrapper = None
        self._tools = tools

        # 阶段1：基础设施绑定（由调度器在启动时调用）
        self._shared_memory = None
        self._message_bus = None
        self._private_memory = None
        self._on_all_analyses_complete = None  # 聚合屏障回调

        # 事件驱动：子类定义订阅的事件类型
        self._subscribed_events: List[str] = []

    @property
    def wrapper(self):
        """获取LangChain Agent包装器（延迟初始化）"""
        if self._wrapper is None:
            from .langchain_agent import LangChainAgentWrapper
            self._wrapper = LangChainAgentWrapper(self, self._tools)
        return self._wrapper

    async def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        与LLM异步对话（返回原始字符串）

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            LLM响应
        """
        return await self.wrapper.achat(message, system_prompt)

    async def chat_structured(
        self,
        prompt_template: Optional[ChatPromptTemplate] = None,
        output_model: Optional[Type[BaseModel]] = None,
        **kwargs,
    ) -> BaseModel:
        """
        使用 LangChain 高级抽象与 LLM 对话，返回结构化 Pydantic 模型。

        流程：
        1. 尝试 prompt_template → llm.with_structured_output(model).ainvoke()
        2. 如果结果为空，fallback 到 raw chat + JSON 解析

        Args:
            prompt_template: ChatPromptTemplate（默认使用 self.prompt_template）
            output_model: 输出 Pydantic 模型类（默认使用 self.output_model）
            **kwargs: 填充 prompt 模板的变量

        Returns:
            Pydantic 模型实例
        """
        import json
        import re

        template = prompt_template or self.prompt_template
        model = output_model or self.output_model

        if template is None:
            raise ValueError(f"{self.__class__.__name__} 未定义 prompt_template")
        if model is None:
            raise ValueError(f"{self.__class__.__name__} 未定义 output_model")

        messages = template.format_messages(**kwargs)

        # 方法1：尝试 with_structured_output
        try:
            structured_llm = self.llm.with_structured_output(model)
            result = await structured_llm.ainvoke(messages)
            # 检查结果是否为空（某些模型可能返回空结果）
            if result and not self._is_empty_result(result):
                return result
            logger.debug("with_structured_output 返回空结果，尝试 fallback")
        except Exception as e:
            logger.debug(f"with_structured_output 失败: {e}，尝试 fallback")

        # 方法2：Fallback — raw chat + JSON 解析
        logger.info(f"[{self.__class__.__name__}] 使用 fallback: raw chat + JSON 解析")
        from src.utils.llm_response import extract_llm_content
        response = await self.llm.ainvoke(messages)
        raw_content = response.content if hasattr(response, 'content') else str(response)
        content = extract_llm_content(raw_content)

        # 清理 markdown 代码块
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = content.strip()

        # 尝试解析 JSON
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # 修复尾部逗号
            fixed = re.sub(r',\s*([}\]])', r'\1', content)
            parsed = json.loads(fixed)

        # 转换为 Pydantic 模型
        return model.model_validate(parsed)

    def _is_empty_result(self, result: BaseModel) -> bool:
        """检查 structured output 结果是否实质为空"""
        data = result.model_dump()
        # 检查是否有非空的列表字段
        for value in data.values():
            if isinstance(value, list) and len(value) > 0:
                return False
            if isinstance(value, dict):
                for v in value.values():
                    if isinstance(v, list) and len(v) > 0:
                        return False
                    if isinstance(v, str) and v:
                        return False
                    if isinstance(v, (int, float)) and v != 0:
                        return False
        return True

    def clear_history(self):
        """清空对话历史"""
        if self._wrapper is not None:
            self._wrapper.clear_history()

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        if self._wrapper is not None:
            return self._wrapper.get_history()
        return []

    # ==================== 阶段1：基础设施绑定 ====================

    def bind_infrastructure(self, shared_memory, message_bus, on_all_complete=None):
        """
        绑定共享内存和消息总线（由调度器在启动时调用）

        Args:
            shared_memory: SharedMemoryManager 或 RuntimeProxy 实例
            message_bus: MessageBus 或 MessageBusProxy 实例
            on_all_complete: 可选回调，聚合屏障归零时调用
        """
        self._shared_memory = shared_memory
        self._message_bus = message_bus
        self._on_all_analyses_complete = on_all_complete
        # 私有记忆只初始化一次（singleton Agent 跨请求共享缓存）
        if self._private_memory is None:
            from src.memory.private_memory import AgentPrivateMemory
            self._private_memory = AgentPrivateMemory(self.agent_id)

        # 事件驱动：自动订阅事件
        for event_type in self._subscribed_events:
            self._message_bus.subscribe_event(event_type, self._on_event_received)
            logger.debug(f"[{self.agent_id}] 订阅事件: {event_type}")

    def read_shared(self, key: str, layer: MemoryLayer) -> Optional[Any]:
        """从共享内存读取数据"""
        if self._shared_memory is None:
            return None
        return self._shared_memory.read(self.agent_id, key, layer)

    def write_shared(self, key: str, value: Any, layer: MemoryLayer, validate: bool = True) -> int:
        """写入共享内存"""
        if self._shared_memory is None:
            return 0
        return self._shared_memory.write(self.agent_id, key, value, layer, validate=validate)

    def decrement_pending_count(self) -> bool:
        """
        递减聚合屏障计数器。

        每个分析 Agent 完成后调用此方法。当计数器归零时返回 True，
        表示所有分析已完成，应触发 ReportGenerator。

        Returns:
            True 如果计数器归零（所有分析完成）
        """
        import logging
        _logger = logging.getLogger(__name__)

        if self._shared_memory is None:
            return False

        current = self._shared_memory.read("coordinator", "_pending_count", MemoryLayer.CONTEXT)
        if current is None or current <= 0:
            return False

        new_count = current - 1
        self._shared_memory.write(
            "coordinator", "_pending_count", new_count, MemoryLayer.CONTEXT,
            validate=False,
        )

        _logger.info(f"[{self.agent_id}] _pending_count: {current} → {new_count}")

        # 归零时触发回调（通知调度器）
        if new_count == 0 and self._on_all_analyses_complete:
            _logger.info(f"[{self.agent_id}] 所有分析完成，触发 ReportGenerator")
            self._on_all_analyses_complete()

        return new_count == 0

    def publish_event(self, event_type: str, data: Dict[str, Any] = None):
        """
        发布业务事件

        Args:
            event_type: 事件类型（使用 BusinessEvent 常量）
            data: 事件附加数据
        """
        if self._message_bus is None:
            return
        from .communication import AgentMessage, MessageType
        content = {"event": event_type}
        if data:
            content.update(data)
        msg = AgentMessage(
            sender_id=self.agent_id,
            receiver_id="*",
            message_type=MessageType.NOTIFICATION,
            content=content,
        )
        self._message_bus.publish(msg)

    def _on_event_received(self, message):
        """
        事件回调（同步）→ 转为异步任务执行

        由 MessageBus 在 publish() 时调用。
        """
        event_type = message.content.get("event") if isinstance(message.content, dict) else None
        session_id = message.content.get("session_id") if isinstance(message.content, dict) else None
        logger.info(f"[{self.agent_id}] 收到事件: {event_type}, session={session_id}")
        asyncio.create_task(self._handle_event(event_type, message.content))

    async def _handle_event(self, event_type: str, data: Dict[str, Any]):
        """
        处理接收到的事件 → 调用 process()

        子类可覆盖此方法实现自定义事件处理逻辑（如聚合屏障）。
        默认行为：检查 _required_agents，不在列表中则跳过。
        """
        # 检查是否在所需 Agent 列表中（按需调度）
        required = self.read_shared("_required_agents", MemoryLayer.CONTEXT)
        if required is not None and self.agent_id not in required:
            logger.debug(f"[{self.agent_id}] 不在 _required_agents 中，跳过")
            return

        task = {"session_id": data.get("session_id")}
        await self.process(task)

    @abstractmethod
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务 (抽象方法)

        Args:
            task: 任务数据

        Returns:
            处理结果
        """
        pass

    async def discuss_topic(self, topic) -> "TopicResponse":
        """
        参与议题讨论（默认实现，子类可覆盖以提供更专业的分析）

        Args:
            topic: Topic 实例

        Returns:
            TopicResponse 实例
        """
        from src.memory.topic_board import TopicResponse
        from src.utils.llm_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""

        # 构建角色特定的 prompt
        role_prompt = self._get_topic_role_prompt()

        system_content = f"""你是一个合同审查专家，你的专业角色是：{self.role}。

{role_prompt}

用户发起以下议题，请从你的专业角度给出分析意见。

规则：
1. 基于合同文本内容进行分析，引用具体条款
2. 给出明确的观点（合理/不合理/有风险/建议修改等）
3. 如果涉及法律条款，引用相关法规
4. 置信度根据分析的确定性打分（0.0-1.0）
5. 回复格式为JSON：{{"opinion": "你的观点", "confidence": 0.8, "references": ["引用的条款或法规"]}}"""

        truncated = contract_text[:12000] if len(contract_text) > 12000 else contract_text
        user_content = f"""合同内容：
{truncated}

议题：{topic.content}"""

        try:
            llm = get_llm()
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]
            response = await llm.ainvoke(messages)
            content = response.content

            # 尝试解析 JSON
            import json
            import re
            json_match = re.search(r'\{[^{}]*"opinion"[^{}]*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "opinion": content[:500],
                    "confidence": 0.7,
                    "references": [],
                }

            return TopicResponse(
                agent_id=self.agent_id,
                agent_name=self.name,
                opinion=result.get("opinion", content[:500]),
                confidence=result.get("confidence", 0.7),
                references=result.get("references", []),
            )
        except Exception as e:
            logger.error(f"[{self.agent_id}] 议题讨论失败: {e}")
            return TopicResponse(
                agent_id=self.agent_id,
                agent_name=self.name,
                opinion=f"分析过程中出现错误: {str(e)}",
                confidence=0.0,
                references=[],
            )

    def _get_topic_role_prompt(self) -> str:
        """获取角色特定的议题讨论 prompt（子类可覆盖）"""
        return f"你是{self.name}，负责{self.role}。请从你的专业角度分析议题。"

    def update_activity(self):
        """更新Agent活跃时间"""
        self.last_active_at = datetime.now()

    def set_running(self, is_running: bool):
        """设置Agent运行状态"""
        self.is_running = is_running
        self.update_activity()

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "is_running": self.is_running,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, name={self.name}, role={self.role})"
