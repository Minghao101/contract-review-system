"""
私有记忆模块 - 每个Agent的独立记忆空间
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from collections import deque
from pathlib import Path
import json


class AgentPrivateMemory:
    """
    Agent私有记忆

    用于存储：
    - 当前任务状态
    - 中间计算结果
    - 上下文窗口管理（支持压缩）
    - 历史决策缓存
    """

    def __init__(self, agent_id: str, max_context_length: int = 100):
        """
        初始化私有记忆

        Args:
            agent_id: Agent ID
            max_context_length: 最大上下文长度
        """
        self.agent_id = agent_id
        self.max_context_length = max_context_length

        # 上下文窗口（对话历史）
        self.context_window: deque = deque(maxlen=max_context_length)

        # 压缩后的摘要（当上下文过长时使用）
        self.compressed_summary: str = ""

        # 任务状态
        self.task_state: Dict[str, Any] = {}

        # 缓存
        self.cache: Dict[str, Any] = {}

        # 创建时间
        self.created_at = datetime.now()

    def update_context(self, role: str, content: str):
        """
        更新上下文窗口

        Args:
            role: 角色 (user/assistant/system)
            content: 内容
        """
        self.context_window.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context(self, last_n: Optional[int] = None) -> List[Dict]:
        """
        获取上下文

        Args:
            last_n: 获取最近N条（None表示全部）

        Returns:
            上下文列表
        """
        if last_n is None:
            return list(self.context_window)
        return list(self.context_window)[-last_n:]

    def compress_context(self) -> str:
        """
        压缩上下文窗口

        当上下文接近最大长度时，将旧内容压缩为摘要

        Returns:
            压缩后的摘要
        """
        if len(self.context_window) < self.max_context_length * 0.8:
            return self.compressed_summary

        # 保留最近20%的内容，压缩旧内容
        keep_count = int(self.max_context_length * 0.2)
        all_items = list(self.context_window)

        # 旧内容压缩为摘要
        old_items = all_items[:-keep_count]
        if old_items:
            summary_parts = []
            for item in old_items:
                summary_parts.append(f"{item['role']}: {item['content'][:50]}...")
            self.compressed_summary = " | ".join(summary_parts)

        # 只保留最近的内容
        self.context_window.clear()
        for item in all_items[-keep_count:]:
            self.context_window.append(item)

        return self.compressed_summary

    def get_full_context(self) -> Dict[str, Any]:
        """
        获取完整上下文（包括压缩摘要）

        Returns:
            包含摘要和最近上下文的字典
        """
        return {
            "compressed_summary": self.compressed_summary,
            "recent_context": list(self.context_window)
        }

    def clear_context(self):
        """清空上下文"""
        self.context_window.clear()
        self.compressed_summary = ""

    def save_to_file(self, file_path: str):
        """
        保存到文件

        Args:
            file_path: 文件路径
        """
        data = {
            "agent_id": self.agent_id,
            "compressed_summary": self.compressed_summary,
            "context_window": list(self.context_window),
            "task_state": self.task_state,
            "cache": {
                k: v for k, v in self.cache.items()
            },
            "created_at": self.created_at.isoformat(),
            "saved_at": datetime.now().isoformat()
        }

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, file_path: str) -> bool:
        """
        从文件加载

        Args:
            file_path: 文件路径

        Returns:
            是否成功加载
        """
        path = Path(file_path)
        if not path.exists():
            return False

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.agent_id = data.get("agent_id", self.agent_id)
            self.compressed_summary = data.get("compressed_summary", "")
            self.task_state = data.get("task_state", {})
            self.cache = data.get("cache", {})

            # 恢复上下文窗口
            self.context_window.clear()
            for item in data.get("context_window", []):
                self.context_window.append(item)

            return True
        except Exception as e:
            print(f"加载记忆文件失败: {e}")
            return False

    def set_task_state(self, task_id: str, state: Dict[str, Any]):
        """
        设置任务状态

        Args:
            task_id: 任务ID
            state: 状态数据
        """
        self.task_state[task_id] = {
            "state": state,
            "updated_at": datetime.now().isoformat()
        }

    def get_task_state(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        if task_id in self.task_state:
            return self.task_state[task_id]["state"]
        return None

    def set_cache(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl_seconds: 过期时间（秒），None表示永不过期
        """
        self.cache[key] = {
            "value": value,
            "created_at": datetime.now().isoformat(),
            "ttl_seconds": ttl_seconds
        }

    def get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self.cache:
            return None

        cache_item = self.cache[key]

        # 检查是否过期
        if cache_item["ttl_seconds"] is not None:
            created_at = datetime.fromisoformat(cache_item["created_at"])
            elapsed = (datetime.now() - created_at).total_seconds()
            if elapsed > cache_item["ttl_seconds"]:
                del self.cache[key]
                return None

        return cache_item["value"]

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()

    def get_status(self) -> Dict[str, Any]:
        """获取记忆状态"""
        return {
            "agent_id": self.agent_id,
            "context_length": len(self.context_window),
            "task_count": len(self.task_state),
            "cache_count": len(self.cache),
            "created_at": self.created_at.isoformat()
        }
