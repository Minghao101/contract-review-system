"""
对话上下文管理器 - 管理多轮对话的状态和历史

功能：
- 对话历史存储和检索
- 上下文注入（历史对话 + 上传文件）
- 意图链追踪
- 对话状态管理
"""
import json
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
import logging
import uuid

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    """对话状态"""
    IDLE = "idle"                          # 空闲
    COLLECTING = "collecting"              # 收集信息中
    PROCESSING = "processing"              # 处理中
    WAITING_CONFIRM = "waiting_confirm"    # 等待确认
    COMPLETED = "completed"                # 已完成
    ERROR = "error"                        # 错误状态


@dataclass
class Message:
    """对话消息"""
    role: str           # user / assistant / system
    content: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


@dataclass
class TurnContext:
    """单轮对话上下文"""
    turn_id: str
    user_message: Message
    assistant_message: Optional[Message] = None
    intent: Optional[str] = None
    intent_confidence: float = 0.0
    agent_results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationContext:
    """
    对话上下文管理器

    管理单个会话的完整上下文，包括：
    - 对话历史
    - 意图链
    - Agent结果缓存
    - 上传文件引用
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        max_history: int = 50,
        max_context_tokens: int = 4000
    ):
        """
        初始化对话上下文

        Args:
            session_id: 会话ID（不提供则自动生成）
            max_history: 最大历史消息数
            max_context_tokens: 最大上下文token数（估算）
        """
        self.max_history = max_history
        self.max_context_tokens = max_context_tokens

        # 对话状态
        self.state = ConversationState.IDLE

        # 历史消息
        self._messages: deque = deque(maxlen=max_history)

        # 轮次上下文
        self._turns: List[TurnContext] = []

        # 当前轮次
        self._current_turn: Optional[TurnContext] = None

        # 上传文件引用
        self._uploaded_files: List[Dict[str, Any]] = []

        # 意图链
        self._intent_chain: List[str] = []

        # 共享数据（Agent间传递）
        self._shared_data: Dict[str, Any] = {}

        # 元数据（必须在session_id赋值之前初始化，因为setter会访问_metadata）
        self._metadata: Dict[str, Any] = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "turn_count": 0,
            "total_messages": 0,
        }

        # session_id通过property setter存储到_metadata中
        self.session_id = session_id or str(uuid.uuid4())

        logger.info(f"对话上下文初始化: session={self.session_id}")

    @property
    def session_id(self) -> str:
        return self._metadata.get("session_id", "")

    @session_id.setter
    def session_id(self, value: str):
        self._metadata["session_id"] = value

    # ==================== 消息管理 ====================

    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加用户消息"""
        msg = Message(role="user", content=content, metadata=metadata or {})
        self._messages.append(msg)
        self._metadata["total_messages"] += 1

        # 开始新轮次
        self._current_turn = TurnContext(
            turn_id=str(uuid.uuid4()),
            user_message=msg
        )
        self.state = ConversationState.COLLECTING

        logger.debug(f"用户消息: {content[:50]}...")

    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加助手消息"""
        msg = Message(role="assistant", content=content, metadata=metadata or {})
        self._messages.append(msg)
        self._metadata["total_messages"] += 1

        # 完成当前轮次
        if self._current_turn:
            self._current_turn.assistant_message = msg
            self._turns.append(self._current_turn)
            self._current_turn = None
            self._metadata["turn_count"] = len(self._turns)

        self.state = ConversationState.COMPLETED

        logger.debug(f"助手消息: {content[:50]}...")

    def add_system_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加系统消息"""
        msg = Message(role="system", content=content, metadata=metadata or {})
        self._messages.append(msg)

    def get_messages(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取消息历史"""
        messages = list(self._messages)
        if last_n:
            messages = messages[-last_n:]
        return [m.to_dict() for m in messages]

    def get_context_messages(self) -> List[Dict[str, str]]:
        """获取用于LLM的上下文消息（role/content格式）"""
        messages = []
        for msg in self._messages:
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    # ==================== 意图管理 ====================

    def set_current_intent(self, intent: str, confidence: float = 0.0):
        """设置当前轮次的意图"""
        if self._current_turn:
            self._current_turn.intent = intent
            self._current_turn.intent_confidence = confidence
        self._intent_chain.append(intent)

        logger.debug(f"意图: {intent} (confidence={confidence:.2f})")

    def get_intent_chain(self) -> List[str]:
        """获取意图链"""
        return list(self._intent_chain)

    def get_last_intent(self) -> Optional[str]:
        """获取上一轮意图"""
        return self._intent_chain[-1] if self._intent_chain else None

    def get_intent_context(self) -> Dict[str, Any]:
        """获取意图识别所需的上下文"""
        return {
            "last_intent": self.get_last_intent(),
            "has_contract_text": bool(self._shared_data.get("contract_text")),
            "turn_count": len(self._turns),
            "state": self.state.value,
        }

    # ==================== Agent结果管理 ====================

    def set_agent_result(self, agent_name: str, result: Dict[str, Any]):
        """设置Agent执行结果（存储在当前轮次中）"""
        if self._current_turn:
            self._current_turn.agent_results[agent_name] = result

        logger.debug(f"Agent结果: {agent_name}")

    def get_agent_result(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """获取最近一次Agent执行结果"""
        for turn in reversed(self._turns):
            if agent_name in turn.agent_results:
                return turn.agent_results[agent_name]
        return None

    def get_all_results(self) -> Dict[str, Any]:
        """获取所有轮次的Agent结果（后轮覆盖前轮同名Agent）"""
        results = {}
        for turn in self._turns:
            for agent_name, result in turn.agent_results.items():
                results[agent_name] = result
        return results

    # ==================== 文件管理 ====================

    def add_uploaded_file(self, filename: str, content: str, file_type: str = ""):
        """添加上传文件引用"""
        file_ref = {
            "filename": filename,
            "content": content,
            "type": file_type,
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._uploaded_files.append(file_ref)

        # 如果是合同文件，存储到共享数据
        if file_type in ["txt", "pdf", "docx"] or filename.endswith((".txt", ".pdf", ".docx")):
            self._shared_data["contract_text"] = content
            self._shared_data["contract_filename"] = filename

        logger.info(f"上传文件: {filename}")

    def get_uploaded_files(self) -> List[Dict[str, Any]]:
        """获取上传文件列表"""
        return [
            {"filename": f["filename"], "type": f["type"], "uploaded_at": f["uploaded_at"]}
            for f in self._uploaded_files
        ]

    def get_contract_text(self) -> Optional[str]:
        """获取合同文本"""
        return self._shared_data.get("contract_text")

    # ==================== 共享数据 ====================

    def set_shared_data(self, key: str, value: Any):
        """设置共享数据"""
        self._shared_data[key] = value

    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """获取共享数据"""
        return self._shared_data.get(key, default)

    # ==================== 上下文构建 ====================

    def build_llm_context(self, include_history: int = 10) -> str:
        """
        构建LLM上下文字符串

        Args:
            include_history: 包含的历史消息数

        Returns:
            上下文字符串
        """
        parts = []

        # 1. 会话信息
        parts.append(f"会话ID: {self.session_id}")
        parts.append(f"当前状态: {self.state.value}")
        parts.append(f"对话轮数: {len(self._turns)}")

        # 2. 意图链
        if self._intent_chain:
            parts.append(f"意图历史: {' -> '.join(self._intent_chain[-5:])}")

        # 3. 上传文件
        if self._uploaded_files:
            files = [f["filename"] for f in self._uploaded_files]
            parts.append(f"已上传文件: {', '.join(files)}")

        # 4. 合同文本
        contract_text = self.get_contract_text()
        if contract_text:
            parts.append(f"合同文本({len(contract_text)}字): {contract_text[:200]}...")

        # 5. 历史消息
        messages = self.get_messages(last_n=include_history)
        if messages:
            parts.append("\n--- 对话历史 ---")
            for msg in messages:
                role = "用户" if msg["role"] == "user" else "助手"
                parts.append(f"{role}: {msg['content'][:200]}")

        # 6. Agent结果摘要
        results = self.get_all_results()
        if results:
            parts.append("\n--- 已有分析结果 ---")
            for agent_name in results:
                parts.append(f"- {agent_name}: 已完成")

        return "\n".join(parts)

    def build_task_context(self) -> Dict[str, Any]:
        """构建任务上下文（用于Agent输入）"""
        context = {
            "session_id": self.session_id,
            "state": self.state.value,
        }

        # 合同文本
        contract_text = self.get_contract_text()
        if contract_text:
            context["contract_text"] = contract_text

        # 历史结果
        context["previous_results"] = self.get_all_results()

        # 上传文件
        if self._uploaded_files:
            context["uploaded_files"] = self.get_uploaded_files()

        return context

    # ==================== 状态管理 ====================

    def set_state(self, state: ConversationState):
        """设置对话状态"""
        old_state = self.state
        self.state = state
        logger.debug(f"状态变更: {old_state.value} -> {state.value}")

    def get_status(self) -> Dict[str, Any]:
        """获取上下文状态"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "turn_count": len(self._turns),
            "total_messages": len(self._messages),
            "intent_chain": self._intent_chain,
            "uploaded_files": len(self._uploaded_files),
            "has_contract": bool(self.get_contract_text()),
            "metadata": self._metadata,
        }

    # ==================== 持久化 ====================

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "messages": [m.to_dict() for m in self._messages],
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "user_message": t.user_message.to_dict(),
                    "assistant_message": t.assistant_message.to_dict() if t.assistant_message else None,
                    "intent": t.intent,
                    "intent_confidence": t.intent_confidence,
                    "agent_results": t.agent_results,
                }
                for t in self._turns
            ],
            "intent_chain": self._intent_chain,
            "uploaded_files": self._uploaded_files,
            "shared_data": {k: v for k, v in self._shared_data.items()
                           if not isinstance(v, (bytes,))},  # 排除二进制数据
            "metadata": self._metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        """从字典反序列化"""
        ctx = cls(session_id=data.get("session_id"))
        ctx.state = ConversationState(data.get("state", "idle"))
        ctx._intent_chain = data.get("intent_chain", [])
        ctx._uploaded_files = data.get("uploaded_files", [])
        ctx._shared_data = data.get("shared_data", {})
        ctx._metadata = data.get("metadata", {})

        # 恢复消息
        for msg_data in data.get("messages", []):
            msg = Message(
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=msg_data.get("timestamp", ""),
                metadata=msg_data.get("metadata", {})
            )
            ctx._messages.append(msg)

        return ctx

    def save_to_file(self, file_path: str):
        """保存到文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"上下文已保存: {file_path}")
        except Exception as e:
            logger.error(f"保存上下文失败: {e}")

    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["ConversationContext"]:
        """从文件加载"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"加载上下文失败: {e}")
            return None

    def clear(self):
        """清空上下文"""
        self._messages.clear()
        self._turns.clear()
        self._current_turn = None
        self._uploaded_files.clear()
        self._intent_chain.clear()
        self._shared_data.clear()
        self.state = ConversationState.IDLE
        self._metadata["turn_count"] = 0
        self._metadata["total_messages"] = 0
        logger.info("上下文已清空")


class ConversationManager:
    """
    对话管理器 - 管理多个会话

    用于多用户场景，每个用户维护独立的对话上下文。
    """

    def __init__(self, max_sessions: int = 100):
        self._sessions: Dict[str, ConversationContext] = {}
        self.max_sessions = max_sessions

    def get_or_create(self, session_id: str) -> ConversationContext:
        """获取或创建会话"""
        if session_id not in self._sessions:
            if len(self._sessions) >= self.max_sessions:
                # 移除最旧的会话
                oldest = min(self._sessions.keys(),
                           key=lambda k: self._sessions[k]._metadata.get("created_at", ""))
                del self._sessions[oldest]

            self._sessions[session_id] = ConversationContext(session_id=session_id)

        return self._sessions[session_id]

    def remove(self, session_id: str) -> bool:
        """移除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return [
            {
                "session_id": ctx.session_id,
                "state": ctx.state.value,
                "turn_count": len(ctx._turns),
                "created_at": ctx._metadata.get("created_at", ""),
            }
            for ctx in self._sessions.values()
        ]

    def get_active_count(self) -> int:
        """获取活跃会话数"""
        return len(self._sessions)
