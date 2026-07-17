"""
议题板模块 - 管理用户发起的多 Agent 讨论议题

支持：
- 用户发起议题，多个 Agent 围绕议题讨论
- 议题追问链（父子议题）
- 议题状态管理（open → discussing → resolved）
- Agent 发言记录
"""
import uuid
import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class TopicStatus(Enum):
    """议题状态"""
    OPEN = "open"            # 刚创建，待讨论
    DISCUSSING = "discussing"  # Agent 讨论中
    RESOLVED = "resolved"    # 已收敛，有结论
    FOLLOW_UP = "follow_up"  # 有关联追问


@dataclass
class TopicResponse:
    """Agent 对议题的回应"""
    agent_id: str
    agent_name: str
    opinion: str
    confidence: float = 0.8
    references: List[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "opinion": self.opinion,
            "confidence": self.confidence,
            "references": self.references,
            "timestamp": self.timestamp,
        }


@dataclass
class Topic:
    """讨论议题"""
    id: str
    title: str
    content: str
    raised_by: str  # "user" / "agent:risk_assessor"
    parent_id: Optional[str] = None
    status: TopicStatus = TopicStatus.OPEN
    responses: List[TopicResponse] = field(default_factory=list)
    conclusion: Optional[str] = None
    created_at: str = ""
    resolved_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "raised_by": self.raised_by,
            "parent_id": self.parent_id,
            "status": self.status.value,
            "responses": [r.to_dict() for r in self.responses],
            "conclusion": self.conclusion,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Topic":
        responses = [
            TopicResponse(**r) for r in data.get("responses", [])
        ]
        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            raised_by=data.get("raised_by", "user"),
            parent_id=data.get("parent_id"),
            status=TopicStatus(data.get("status", "open")),
            responses=responses,
            conclusion=data.get("conclusion"),
            created_at=data.get("created_at", ""),
            resolved_at=data.get("resolved_at"),
        )


class TopicBoard:
    """
    议题板 - 管理所有讨论议题

    存储在 SharedMemoryManager 的 CONTEXT 层，key 为 "topic_board"。
    所有 Agent 可见，可读写。
    """

    def __init__(self):
        self._topics: Dict[str, Topic] = {}

    def create_topic(
        self,
        content: str,
        raised_by: str = "user",
        parent_id: Optional[str] = None,
    ) -> Topic:
        """
        创建新议题

        Args:
            content: 用户原始问题
            raised_by: 发起者 ("user" / "agent:xxx")
            parent_id: 父议题 ID（追问时使用）

        Returns:
            新创建的 Topic
        """
        topic_id = str(uuid.uuid4())[:8]
        title = self._extract_title(content)

        topic = Topic(
            id=topic_id,
            title=title,
            content=content,
            raised_by=raised_by,
            parent_id=parent_id,
            status=TopicStatus.OPEN,
        )
        self._topics[topic_id] = topic

        # 如果是追问，将父议题标记为 FOLLOW_UP
        if parent_id and parent_id in self._topics:
            self._topics[parent_id].status = TopicStatus.FOLLOW_UP

        logger.info(f"创建议题: {topic_id} - {title}")
        return topic

    def add_response(self, topic_id: str, response: TopicResponse):
        """Agent 发言"""
        if topic_id not in self._topics:
            logger.warning(f"议题不存在: {topic_id}")
            return
        self._topics[topic_id].responses.append(response)
        self._topics[topic_id].status = TopicStatus.DISCUSSING

    def resolve_topic(self, topic_id: str, conclusion: str):
        """标记议题已解决"""
        if topic_id not in self._topics:
            return
        self._topics[topic_id].conclusion = conclusion
        self._topics[topic_id].status = TopicStatus.RESOLVED
        self._topics[topic_id].resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        return self._topics.get(topic_id)

    def get_all_topics(self) -> List[Topic]:
        return list(self._topics.values())

    def get_latest_topic(self) -> Optional[Topic]:
        """获取最新的议题"""
        if not self._topics:
            return None
        return list(self._topics.values())[-1]

    def is_discussion_complete(self, topic_id: str, required_agents: List[str]) -> bool:
        """所有指定 Agent 都已发言"""
        topic = self._topics.get(topic_id)
        if not topic:
            return False
        responded = {r.agent_id for r in topic.responses}
        return all(a in responded for a in required_agents)

    def to_dict(self) -> Dict[str, Any]:
        """序列化（用于存入 SharedMemory）"""
        return {
            "topics": [t.to_dict() for t in self._topics.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicBoard":
        """从字典反序列化"""
        board = cls()
        for t_data in data.get("topics", []):
            topic = Topic.from_dict(t_data)
            board._topics[topic.id] = topic
        return board

    def _extract_title(self, content: str) -> str:
        """从用户问题中提取议题标题"""
        # 简单处理：取前 50 个字符
        title = content.strip()
        if len(title) > 50:
            title = title[:50] + "..."
        return title
