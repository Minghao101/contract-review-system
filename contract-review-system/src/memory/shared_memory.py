"""
共享记忆模块 - Agent间共享记忆管理
"""
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from threading import Lock
import json
import hashlib

from .memory_layer import MemoryLayer


class MemoryEntry:
    """记忆条目"""

    def __init__(
        self,
        agent_id: str,
        key: str,
        value: Any,
        layer: MemoryLayer,
        version: int = 1
    ):
        self.agent_id = agent_id
        self.key = key
        self.value = value
        self.layer = layer
        self.version = version
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "key": self.key,
            "value": self.value,
            "layer": self.layer.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class SharedMemoryManager:
    """
    共享记忆管理器

    功能：
    - 分层存储（CONTEXT/ANALYSIS/DECISION）
    - 版本控制
    - 读写锁（线程安全）
    - 变更通知（观察者模式）
    """

    def __init__(self, contract_id: str):
        """
        初始化共享记忆管理器

        Args:
            contract_id: 合同ID（用于隔离不同合同的记忆）
        """
        self.contract_id = contract_id

        # 存储结构: {layer: {key: MemoryEntry}}
        self._store: Dict[MemoryLayer, Dict[str, MemoryEntry]] = {
            MemoryLayer.CONTEXT: {},
            MemoryLayer.ANALYSIS: {},
            MemoryLayer.DECISION: {}
        }

        # 读写锁
        self._lock = Lock()

        # 订阅者: {key: [callback1, callback2]}
        self._subscribers: Dict[str, List[Callable]] = {}

    def write(
        self,
        agent_id: str,
        key: str,
        value: Any,
        layer: MemoryLayer
    ) -> int:
        """
        写入共享记忆

        Args:
            agent_id: 写入的Agent ID
            key: 记忆键
            value: 记忆值
            layer: 记忆层次

        Returns:
            版本号
        """
        with self._lock:
            # 检查是否已存在
            if key in self._store[layer]:
                existing = self._store[layer][key]
                # 版本号+1
                new_version = existing.version + 1
                existing.value = value
                existing.agent_id = agent_id
                existing.version = new_version
                existing.updated_at = datetime.now()
            else:
                # 新建
                new_version = 1
                self._store[layer][key] = MemoryEntry(
                    agent_id=agent_id,
                    key=key,
                    value=value,
                    layer=layer,
                    version=new_version
                )

            # 通知订阅者
            self._notify_subscribers(key, agent_id, value)

            return new_version

    def read(
        self,
        agent_id: str,
        key: str,
        layer: MemoryLayer
    ) -> Optional[Any]:
        """
        读取共享记忆

        Args:
            agent_id: 读取的Agent ID
            key: 记忆键
            layer: 记忆层次

        Returns:
            记忆值，不存在返回None
        """
        with self._lock:
            if key in self._store[layer]:
                entry = self._store[layer][key]
                return entry.value
            return None

    def read_with_meta(
        self,
        agent_id: str,
        key: str,
        layer: MemoryLayer
    ) -> Optional[MemoryEntry]:
        """
        读取共享记忆（包含元数据）

        Returns:
            MemoryEntry对象
        """
        with self._lock:
            if key in self._store[layer]:
                return self._store[layer][key]
            return None

    def query(
        self,
        agent_id: str,
        layer: MemoryLayer,
        prefix: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询共享记忆

        Args:
            agent_id: 查询的Agent ID
            layer: 记忆层次
            prefix: 键前缀过滤

        Returns:
            {key: value} 字典
        """
        with self._lock:
            result = {}
            for key, entry in self._store[layer].items():
                if prefix is None or key.startswith(prefix):
                    result[key] = entry.value
            return result

    def delete(
        self,
        agent_id: str,
        key: str,
        layer: MemoryLayer
    ) -> bool:
        """
        删除共享记忆

        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._store[layer]:
                del self._store[layer][key]
                return True
            return False

    def subscribe(self, key: str, callback: Callable):
        """
        订阅记忆变更

        Args:
            key: 记忆键
            callback: 回调函数 callback(key, agent_id, value)
        """
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)

    def unsubscribe(self, key: str, callback: Callable):
        """取消订阅"""
        if key in self._subscribers:
            self._subscribers[key] = [
                cb for cb in self._subscribers[key] if cb != callback
            ]

    def _notify_subscribers(self, key: str, agent_id: str, value: Any):
        """通知订阅者"""
        if key in self._subscribers:
            for callback in self._subscribers[key]:
                try:
                    callback(key, agent_id, value)
                except Exception as e:
                    print(f"通知订阅者失败: {e}")

    def get_all_keys(self, layer: MemoryLayer) -> List[str]:
        """获取指定层次的所有键"""
        with self._lock:
            return list(self._store[layer].keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        with self._lock:
            return {
                "contract_id": self.contract_id,
                "context_count": len(self._store[MemoryLayer.CONTEXT]),
                "analysis_count": len(self._store[MemoryLayer.ANALYSIS]),
                "decision_count": len(self._store[MemoryLayer.DECISION]),
                "subscriber_count": len(self._subscribers)
            }

    def export_all(self) -> Dict[str, Any]:
        """导出所有记忆（用于持久化）"""
        with self._lock:
            result = {}
            for layer in MemoryLayer:
                result[layer.value] = {
                    key: entry.to_dict()
                    for key, entry in self._store[layer].items()
                }
            return result
