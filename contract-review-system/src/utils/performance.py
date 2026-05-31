"""
性能优化模块 - 提供缓存、限流、性能监控等工具

优化策略:
1. LLM实例缓存 - 避免重复创建
2. Agent结果缓存 - 避免重复计算
3. 读写锁优化 - 提升并发性能
4. 消息队列限流 - 防止内存溢出
5. 性能监控 - 记录关键指标
"""
import time
import hashlib
import threading
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps
from collections import OrderedDict
from datetime import datetime, timedelta


# ============================================================
# 1. LLM实例缓存
# ============================================================

class LLMCache:
    """
    LLM实例缓存

    避免每次创建Agent时都新建LLM实例
    """

    _cache: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, provider: str = "default") -> Any:
        """获取缓存的LLM实例"""
        with cls._lock:
            if provider not in cls._cache:
                from src.utils.llm_factory import LLMFactory
                factory = LLMFactory()
                cls._cache[provider] = factory.create_llm()
            return cls._cache[provider]

    @classmethod
    def clear(cls):
        """清空缓存"""
        with cls._lock:
            cls._cache.clear()

    @classmethod
    def size(cls) -> int:
        """获取缓存大小"""
        return len(cls._cache)


# ============================================================
# 2. Agent结果缓存 (LRU)
# ============================================================

class AgentResultCache:
    """
    Agent结果缓存 (LRU策略)

    对相同输入的Agent调用缓存结果，避免重复LLM调用
    """

    def __init__(self, max_size: int = 128, ttl_seconds: int = 3600):
        """
        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间(秒)
        """
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, agent_id: str, task: Dict[str, Any]) -> str:
        """生成缓存键"""
        content = f"{agent_id}:{sorted(task.items())}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, agent_id: str, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取缓存结果"""
        key = self._make_key(agent_id, task)
        with self._lock:
            if key in self._cache:
                # 检查是否过期
                if time.time() - self._timestamps[key] < self._ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return self._cache[key]
                else:
                    # 过期，删除
                    del self._cache[key]
                    del self._timestamps[key]

            self._misses += 1
            return None

    def set(self, agent_id: str, task: Dict[str, Any], result: Dict[str, Any]):
        """设置缓存"""
        key = self._make_key(agent_id, task)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    # 淘汰最旧的
                    oldest_key, _ = self._cache.popitem(last=False)
                    del self._timestamps[oldest_key]

            self._cache[key] = result
            self._timestamps[key] = time.time()

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self._hits / total * 100:.1f}%" if total > 0 else "N/A"
            }


# ============================================================
# 3. 消息队列限流
# ============================================================

class BoundedMessageQueue:
    """
    有界消息队列

    防止MessageBus消息无限增长导致内存溢出
    """

    def __init__(self, max_size: int = 10000, max_age_seconds: int = 3600):
        """
        Args:
            max_size: 最大队列长度
            max_age_seconds: 消息最大存活时间(秒)
        """
        self._queue: list = []
        self._max_size = max_size
        self._max_age = max_age_seconds
        self._lock = threading.Lock()
        self._dropped_count = 0

    def push(self, message: Any):
        """推入消息"""
        with self._lock:
            self._queue.append({
                "message": message,
                "timestamp": time.time()
            })

            # 超出容量限制，移除最旧的
            while len(self._queue) > self._max_size:
                self._queue.pop(0)
                self._dropped_count += 1

    def get_all(self) -> list:
        """获取所有未过期消息"""
        with self._lock:
            cutoff = time.time() - self._max_age
            self._queue = [
                msg for msg in self._queue
                if msg["timestamp"] > cutoff
            ]
            return [msg["message"] for msg in self._queue]

    def clear(self):
        """清空队列"""
        with self._lock:
            self._queue.clear()

    def size(self) -> int:
        """当前队列大小"""
        return len(self._queue)

    def stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "size": len(self._queue),
            "max_size": self._max_size,
            "dropped_count": self._dropped_count
        }


# ============================================================
# 4. 性能监控装饰器
# ============================================================

class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self):
        self._metrics: Dict[str, list] = {}
        self._lock = threading.Lock()

    def record(self, name: str, duration: float, extra: Dict[str, Any] = None):
        """记录一次性能指标"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = []

            entry = {
                "duration": duration,
                "timestamp": time.time()
            }
            if extra:
                entry.update(extra)

            self._metrics[name].append(entry)

            # 保留最近1000条
            if len(self._metrics[name]) > 1000:
                self._metrics[name] = self._metrics[name][-1000:]

    def get_stats(self, name: str) -> Dict[str, Any]:
        """获取指定指标的统计"""
        with self._lock:
            if name not in self._metrics or not self._metrics[name]:
                return {"count": 0}

            durations = [e["duration"] for e in self._metrics[name]]
            return {
                "count": len(durations),
                "avg": sum(durations) / len(durations),
                "min": min(durations),
                "max": max(durations),
                "total": sum(durations),
                "p50": sorted(durations)[len(durations) // 2],
                "p95": sorted(durations)[int(len(durations) * 0.95)] if len(durations) >= 20 else max(durations),
                "p99": sorted(durations)[int(len(durations) * 0.99)] if len(durations) >= 100 else max(durations),
            }

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有指标统计"""
        with self._lock:
            return {
                name: self.get_stats(name)
                for name in self._metrics
            }

    def clear(self):
        """清空所有指标"""
        with self._lock:
            self._metrics.clear()


# 全局性能指标实例
perf_metrics = PerformanceMetrics()


def monitor_performance(name: str = None):
    """
    性能监控装饰器

    Usage:
        @monitor_performance("agent_process")
        async def process(self, task):
            ...
    """
    def decorator(func: Callable):
        metric_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                perf_metrics.record(metric_name, duration, {"status": "success"})
                return result
            except Exception as e:
                duration = time.time() - start
                perf_metrics.record(metric_name, duration, {"status": "error", "error": str(e)})
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                perf_metrics.record(metric_name, duration, {"status": "success"})
                return result
            except Exception as e:
                duration = time.time() - start
                perf_metrics.record(metric_name, duration, {"status": "error", "error": str(e)})
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================
# 5. 批量处理优化
# ============================================================

class BatchProcessor:
    """
    批量处理器

    将多个小任务合并为批次执行，减少LLM调用次数
    """

    def __init__(self, batch_size: int = 5, flush_interval: float = 1.0):
        """
        Args:
            batch_size: 批次大小
            flush_interval: 刷新间隔(秒)
        """
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: list = []
        self._last_flush = time.time()
        self._lock = threading.Lock()

    def add(self, item: Any) -> bool:
        """
        添加任务到缓冲区

        Returns:
            是否触发了批次处理
        """
        with self._lock:
            self._buffer.append(item)

            if len(self._buffer) >= self._batch_size:
                return True
            if time.time() - self._last_flush >= self._flush_interval:
                return True
            return False

    def flush(self) -> list:
        """获取并清空缓冲区"""
        with self._lock:
            items = self._buffer[:]
            self._buffer.clear()
            self._last_flush = time.time()
            return items

    def size(self) -> int:
        """当前缓冲区大小"""
        return len(self._buffer)


# ============================================================
# 6. 连接池 (用于未来Redis/数据库连接)
# ============================================================

class SimpleConnectionPool:
    """
    简单连接池

    管理可复用的连接资源
    """

    def __init__(self, factory: Callable, max_size: int = 10):
        """
        Args:
            factory: 连接工厂函数
            max_size: 最大连接数
        """
        self._factory = factory
        self._max_size = max_size
        self._pool: list = []
        self._in_use = 0
        self._lock = threading.Lock()

    def acquire(self) -> Any:
        """获取连接"""
        with self._lock:
            if self._pool:
                return self._pool.pop()
            if self._in_use < self._max_size:
                self._in_use += 1
                return self._factory()
            raise RuntimeError("Connection pool exhausted")

    def release(self, conn: Any):
        """释放连接"""
        with self._lock:
            self._in_use -= 1
            if len(self._pool) < self._max_size:
                self._pool.append(conn)

    def stats(self) -> Dict[str, Any]:
        """获取连接池统计"""
        return {
            "available": len(self._pool),
            "in_use": self._in_use,
            "max_size": self._max_size
        }
