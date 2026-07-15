"""
基础Agent模块 - 定义所有Agent的基类

增强功能（阶段1弱中心化）：
- bind_infrastructure(): 绑定共享内存和消息总线
- read_shared() / write_shared(): 读写共享内存
- publish_event(): 发布业务事件
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
import logging
from langchain_core.language_models import BaseLLM

from src.utils.llm_factory import get_llm
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Agent基类

    所有专业Agent都应继承此类并实现抽象方法
    """

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
        与LLM异步对话

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            LLM响应
        """
        return await self.wrapper.achat(message, system_prompt)

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
