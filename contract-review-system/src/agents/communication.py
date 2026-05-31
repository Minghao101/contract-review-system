"""
Agent通信模块 - 定义Agent间通信协议
"""
from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum
import uuid


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
    """消息总线 - 管理Agent间消息传递"""

    def __init__(self):
        self._subscribers: Dict[str, list] = {}
        self._message_queue: list = []

    def subscribe(self, agent_id: str, callback):
        """
        订阅消息

        Args:
            agent_id: Agent ID
            callback: 回调函数
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback=None):
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

    def publish(self, message: AgentMessage):
        """
        发布消息

        Args:
            message: 消息对象
        """
        self._message_queue.append(message)

        # 通知订阅者
        if message.receiver_id in self._subscribers:
            for callback in self._subscribers[message.receiver_id]:
                callback(message)

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


# 全局消息总线实例
message_bus = MessageBus()
