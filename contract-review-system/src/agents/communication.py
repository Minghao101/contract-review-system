"""
Agent通信模块 - 定义Agent间通信协议

增强功能：
- publish_async(): 异步发布（Agent 事件驱动协作）
- 事件历史记录（调试用）
- clear(): 会话结束时清理订阅和历史
"""
from typing import Any, Callable, Dict, Optional
from datetime import datetime
from enum import Enum
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    TASK_ASSIGN = "task_assign"          # 任务分配
    TASK_RESULT = "task_result"          # 任务结果
    QUERY = "query"                      # 查询请求
    RESPONSE = "response"                # 查询响应
    NOTIFICATION = "notification"        # 通知
    ERROR = "error"                      # 错误


class AgentMessage:
    """Agent间通信消息"""

    def __init__(
        self,
        sender_id: str,
        receiver_id: str,
        message_type: MessageType,
        content: Dict[str, Any],
        correlation_id: Optional[str] = None
    ):
        """
        初始化消息

        Args:
            sender_id: 发送者ID
            receiver_id: 接收者ID
            message_type: 消息类型
            content: 消息内容
            correlation_id: 关联ID (用于请求-响应匹配)
        """
        self.message_id = str(uuid.uuid4())
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.message_type = message_type
        self.content = content
        self.correlation_id = correlation_id or self.message_id
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """从字典创建消息"""
        return cls(
            sender_id=data["sender_id"],
            receiver_id=data["receiver_id"],
            message_type=MessageType(data["message_type"]),
            content=data["content"],
            correlation_id=data.get("correlation_id"),
        )

    def __repr__(self) -> str:
        return f"AgentMessage(type={self.message_type.value}, from={self.sender_id}, to={self.receiver_id})"


class MessageBus:
    """
    消息总线 - 管理Agent间消息传递

    支持：
    - 同步发布 publish()
    - 异步发布 publish_async()（Agent 事件驱动协作）
    - 事件历史记录（调试用）
    - 订阅管理（支持通配符接收者 "*"）
    - clear() 清理（会话结束时）
    """

    def __init__(self):
        self._subscribers: Dict[str, list] = {}
        self._event_subscribers: Dict[str, list] = {}  # 按事件类型订阅
        self._message_queue: list = []
        self._event_history: list = []  # 事件历史（调试用）

    def subscribe(self, agent_id: str, callback: Callable):
        """
        订阅消息

        Args:
            agent_id: Agent ID（"*" 表示订阅所有消息）
            callback: 回调函数 callback(message)
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: Callable = None):
        """
        取消订阅

        Args:
            agent_id: Agent ID
            callback: 可选，指定要移除的回调函数。若为None则移除该agent所有订阅
        """
        if agent_id not in self._subscribers:
            return
        if callback is not None:
            self._subscribers[agent_id] = [
                cb for cb in self._subscribers[agent_id] if cb != callback
            ]
            if not self._subscribers[agent_id]:
                del self._subscribers[agent_id]
        else:
            del self._subscribers[agent_id]

    def subscribe_event(self, event_type: str, callback: Callable):
        """
        订阅特定事件类型（事件驱动协作的核心机制）

        Args:
            event_type: 事件类型（如 "task.created", "document.parsed"）
            callback: 回调函数 callback(message)
        """
        if event_type not in self._event_subscribers:
            self._event_subscribers[event_type] = []
        self._event_subscribers[event_type].append(callback)

    def unsubscribe_event(self, event_type: str, callback: Callable = None):
        """取消事件类型订阅"""
        if event_type not in self._event_subscribers:
            return
        if callback is not None:
            self._event_subscribers[event_type] = [
                cb for cb in self._event_subscribers[event_type] if cb != callback
            ]
            if not self._event_subscribers[event_type]:
                del self._event_subscribers[event_type]
        else:
            del self._event_subscribers[event_type]

    def _notify_callbacks(self, callbacks: list, message: AgentMessage):
        """通知回调列表（同步）"""
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"消息回调失败: {e}")

    async def _notify_callbacks_async(self, callbacks: list, message: AgentMessage):
        """通知回调列表（异步，自动处理同步/异步回调）"""
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"异步消息回调失败: {e}")

    def _get_matching_callbacks(self, message: AgentMessage) -> tuple:
        """获取匹配的订阅者回调列表"""
        agent_callbacks = []
        for agent_id, callbacks in self._subscribers.items():
            if agent_id == message.receiver_id or agent_id == "*":
                agent_callbacks.extend(callbacks)

        event_callbacks = []
        event_type = message.content.get("event") if isinstance(message.content, dict) else None
        if event_type and event_type in self._event_subscribers:
            event_callbacks.extend(self._event_subscribers[event_type])

        return agent_callbacks, event_callbacks

    def publish(self, message: AgentMessage):
        """同步发布消息"""
        self._message_queue.append(message)
        self._record_event(message)
        agent_callbacks, event_callbacks = self._get_matching_callbacks(message)
        self._notify_callbacks(agent_callbacks, message)
        self._notify_callbacks(event_callbacks, message)

    async def publish_async(self, message: AgentMessage):
        """异步发布消息"""
        self._message_queue.append(message)
        self._record_event(message)
        agent_callbacks, event_callbacks = self._get_matching_callbacks(message)
        await self._notify_callbacks_async(agent_callbacks, message)
        await self._notify_callbacks_async(event_callbacks, message)

    def _record_event(self, message: AgentMessage):
        """记录事件历史（调试用）"""
        self._event_history.append({
            "message_id": message.message_id,
            "sender": message.sender_id,
            "receiver": message.receiver_id,
            "type": message.message_type.value,
            "content_keys": list(message.content.keys()) if isinstance(message.content, dict) else [],
            "timestamp": message.timestamp.isoformat(),
        })
        # 只保留最近 100 条
        if len(self._event_history) > 100:
            self._event_history = self._event_history[-100:]

    def get_event_history(self, limit: int = 50) -> list:
        """获取事件历史（调试用）"""
        return self._event_history[-limit:]

    def get_messages(self, agent_id: str) -> list:
        """获取指定Agent的消息"""
        return [
            msg for msg in self._message_queue
            if msg.receiver_id == agent_id
        ]

    def clear_messages(self, agent_id: str):
        """清除指定Agent的消息"""
        self._message_queue = [
            msg for msg in self._message_queue
            if msg.receiver_id != agent_id
        ]

    def clear(self):
        """清理所有订阅和消息（会话结束时调用）"""
        self._subscribers.clear()
        self._event_subscribers.clear()
        self._message_queue.clear()
        self._event_history.clear()


# 全局消息总线实例
message_bus = MessageBus()
