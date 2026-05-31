"""
Day 19: 性能优化测试
测试缓存、限流、性能监控、批量处理等优化组件
"""
import sys
import time
import asyncio
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.performance import (
    LLMCache,
    AgentResultCache,
    BoundedMessageQueue,
    PerformanceMetrics,
    monitor_performance,
    BatchProcessor,
    SimpleConnectionPool,
    perf_metrics,
)


# ============================================================
# 1. LLM缓存测试
# ============================================================

def test_llm_cache():
    """测试LLM实例缓存"""
    print("  [1/10] LLM缓存...")

    # 清空缓存
    LLMCache.clear()
    assert LLMCache.size() == 0
    print("    ✓ 缓存初始化为空")

    # 获取LLM实例（应创建新实例）
    llm1 = LLMCache.get("test_provider")
    assert llm1 is not None
    assert LLMCache.size() == 1
    print("    ✓ 首次获取创建新实例")

    # 再次获取（应返回缓存实例）
    llm2 = LLMCache.get("test_provider")
    assert llm1 is llm2  # 同一对象
    assert LLMCache.size() == 1
    print("    ✓ 再次获取返回缓存实例")

    # 不同provider
    llm3 = LLMCache.get("another_provider")
    assert llm3 is not llm1
    assert LLMCache.size() == 2
    print("    ✓ 不同provider独立缓存")

    # 清空
    LLMCache.clear()
    assert LLMCache.size() == 0
    print("    ✓ 缓存清空成功")

    print("    ✓ LLM缓存测试通过")
    return True


# ============================================================
# 2. Agent结果缓存测试
# ============================================================

def test_agent_result_cache():
    """测试Agent结果LRU缓存"""
    print("  [2/10] Agent结果缓存...")

    cache = AgentResultCache(max_size=3, ttl_seconds=60)

    task1 = {"contract_text": "合同A", "type": "service"}
    task2 = {"contract_text": "合同B", "type": "service"}
    task3 = {"contract_text": "合同C", "type": "service"}

    result1 = {"status": "completed", "score": 85}
    result2 = {"status": "completed", "score": 72}
    result3 = {"status": "completed", "score": 90}

    # 缓存未命中
    assert cache.get("agent_1", task1) is None
    print("    ✓ 缓存未命中返回None")

    # 设置缓存
    cache.set("agent_1", task1, result1)
    cache.set("agent_1", task2, result2)
    cache.set("agent_1", task3, result3)
    assert cache.stats()["size"] == 3
    print("    ✓ 设置3个缓存条目")

    # 缓存命中
    hit = cache.get("agent_1", task1)
    assert hit == result1
    print("    ✓ 缓存命中返回正确结果")

    # LRU淘汰（添加第4个，淘汰最旧的）
    task4 = {"contract_text": "合同D", "type": "service"}
    result4 = {"status": "completed", "score": 60}
    cache.set("agent_1", task4, result4)

    stats = cache.stats()
    assert stats["size"] == 3
    print("    ✓ LRU淘汰: 新条目加入，最旧被淘汰")

    # 验证task2被淘汰（最旧未访问）
    assert cache.get("agent_1", task2) is None
    print("    ✓ 最旧条目已被淘汰")

    # 不同agent独立缓存
    cache.set("agent_2", task1, {"score": 95})
    hit2 = cache.get("agent_2", task1)
    assert hit2["score"] == 95
    print("    ✓ 不同agent独立缓存")

    # 统计
    stats = cache.stats()
    assert stats["hits"] > 0
    print(f"    ✓ 命中率: {stats['hit_rate']}")

    print("    ✓ Agent结果缓存测试通过")
    return True


# ============================================================
# 3. 有界消息队列测试
# ============================================================

def test_bounded_message_queue():
    """测试有界消息队列"""
    print("  [3/10] 有界消息队列...")

    queue = BoundedMessageQueue(max_size=5, max_age_seconds=60)

    # 推入消息
    for i in range(5):
        queue.push(f"msg_{i}")
    assert queue.size() == 5
    print("    ✓ 推入5条消息")

    # 超出容量，最旧的被淘汰
    queue.push("msg_5")
    messages = queue.get_all()
    assert queue.size() == 5
    assert messages[0] == "msg_1"  # msg_0被淘汰
    print("    ✓ 超出容量时淘汰最旧消息")

    # 统计
    stats = queue.stats()
    assert stats["dropped_count"] >= 1
    print(f"    ✓ 丢弃计数: {stats['dropped_count']}")

    # 清空
    queue.clear()
    assert queue.size() == 0
    print("    ✓ 队列清空成功")

    print("    ✓ 有界消息队列测试通过")
    return True


# ============================================================
# 4. 性能监控测试
# ============================================================

def test_performance_metrics():
    """测试性能指标收集器"""
    print("  [4/10] 性能指标...")

    metrics = PerformanceMetrics()

    # 记录指标
    for i in range(10):
        metrics.record("test_operation", 0.1 * (i + 1))

    stats = metrics.get_stats("test_operation")
    assert stats["count"] == 10
    assert stats["min"] == 0.1
    assert stats["max"] == 1.0
    assert abs(stats["avg"] - 0.55) < 0.01
    print(f"    ✓ 记录10次, 平均: {stats['avg']:.2f}s")

    # 百分位
    assert stats["p50"] > 0
    print(f"    ✓ P50: {stats['p50']:.2f}s, P95: {stats['p95']:.2f}s")

    # 不存在的指标
    empty = metrics.get_stats("nonexistent")
    assert empty["count"] == 0
    print("    ✓ 不存在的指标返回count=0")

    # 所有指标
    metrics.record("another_op", 0.05)
    all_stats = metrics.get_all_stats()
    assert "test_operation" in all_stats
    assert "another_op" in all_stats
    print(f"    ✓ 所有指标数: {len(all_stats)}")

    # 清空
    metrics.clear()
    assert metrics.get_stats("test_operation")["count"] == 0
    print("    ✓ 指标清空成功")

    print("    ✓ 性能指标测试通过")
    return True


# ============================================================
# 5. 性能监控装饰器测试
# ============================================================

def test_monitor_decorator():
    """测试性能监控装饰器"""
    print("  [5/10] 性能监控装饰器...")

    # 清空全局指标
    perf_metrics.clear()

    @monitor_performance("test_sync_op")
    def sync_operation():
        time.sleep(0.01)
        return "done"

    @monitor_performance("test_async_op")
    async def async_operation():
        await asyncio.sleep(0.01)
        return "done"

    # 同步装饰器
    result = sync_operation()
    assert result == "done"
    print("    ✓ 同步装饰器执行正常")

    # 异步装饰器
    result = asyncio.run(async_operation())
    assert result == "done"
    print("    ✓ 异步装饰器执行正常")

    # 检查全局指标
    sync_stats = perf_metrics.get_stats("test_sync_op")
    assert sync_stats["count"] >= 1
    assert sync_stats["avg"] >= 0.01
    print(f"    ✓ 同步操作记录: {sync_stats['count']}次, 平均{sync_stats['avg']:.3f}s")

    async_stats = perf_metrics.get_stats("test_async_op")
    assert async_stats["count"] >= 1
    print(f"    ✓ 异步操作记录: {async_stats['count']}次, 平均{async_stats['avg']:.3f}s")

    print("    ✓ 性能监控装饰器测试通过")
    return True


# ============================================================
# 6. 批量处理器测试
# ============================================================

def test_batch_processor():
    """测试批量处理器"""
    print("  [6/10] 批量处理器...")

    processor = BatchProcessor(batch_size=3, flush_interval=0.1)

    # 添加项目，未达到批次大小
    assert processor.add("item_1") is False
    assert processor.add("item_2") is False
    assert processor.size() == 2
    print("    ✓ 添加2项，未触发批次")

    # 达到批次大小
    assert processor.add("item_3") is True
    print("    ✓ 添加第3项，触发批次")

    # flush获取并清空
    items = processor.flush()
    assert len(items) == 3
    assert processor.size() == 0
    print(f"    ✓ Flush获取{len(items)}项，缓冲区清空")

    # 时间触发
    processor.add("item_a")
    time.sleep(0.15)
    assert processor.add("item_b") is True
    items = processor.flush()
    assert len(items) == 2
    print("    ✓ 时间间隔触发批次")

    print("    ✓ 批量处理器测试通过")
    return True


# ============================================================
# 7. 连接池测试
# ============================================================

def test_connection_pool():
    """测试简单连接池"""
    print("  [7/10] 连接池...")

    conn_id = [0]

    def create_conn():
        conn_id[0] += 1
        return f"conn_{conn_id[0]}"

    pool = SimpleConnectionPool(create_conn, max_size=3)

    # 获取连接
    c1 = pool.acquire()
    c2 = pool.acquire()
    assert c1 != c2
    print("    ✓ 获取2个不同连接")

    stats = pool.stats()
    assert stats["in_use"] == 2
    assert stats["available"] == 0
    print(f"    ✓ 使用中: {stats['in_use']}, 可用: {stats['available']}")

    # 释放连接
    pool.release(c1)
    c3 = pool.acquire()
    assert c3 == c1  # 复用已释放的连接
    print("    ✓ 释放后复用连接")

    # 达到上限
    pool.acquire()  # c2, c3 in use
    pool.release(c2)
    pool.release(c3)
    c4 = pool.acquire()
    c5 = pool.acquire()
    c6 = pool.acquire()
    try:
        pool.acquire()  # 应该失败
        assert False, "应该抛出异常"
    except RuntimeError:
        print("    ✓ 连接池耗尽时抛出异常")

    # 释放所有
    pool.release(c4)
    pool.release(c5)
    pool.release(c6)
    stats = pool.stats()
    assert stats["in_use"] == 0
    print("    ✓ 全部释放后状态正确")

    print("    ✓ 连接池测试通过")
    return True


# ============================================================
# 8. 并发安全测试
# ============================================================

def test_concurrent_safety():
    """测试并发安全性"""
    print("  [8/10] 并发安全...")

    from concurrent.futures import ThreadPoolExecutor

    cache = AgentResultCache(max_size=100, ttl_seconds=60)
    queue = BoundedMessageQueue(max_size=1000)
    metrics = PerformanceMetrics()

    errors = []

    def concurrent_cache_ops(i):
        try:
            task = {"task_id": i}
            result = {"result": i * 2}
            cache.set(f"agent_{i % 5}", task, result)
            cache.get(f"agent_{i % 5}", task)
        except Exception as e:
            errors.append(str(e))

    def concurrent_queue_ops(i):
        try:
            queue.push(f"msg_{i}")
            queue.get_all()
            queue.size()
        except Exception as e:
            errors.append(str(e))

    def concurrent_metrics_ops(i):
        try:
            metrics.record("concurrent_test", i * 0.001)
            metrics.get_stats("concurrent_test")
        except Exception as e:
            errors.append(str(e))

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(100):
            futures.append(executor.submit(concurrent_cache_ops, i))
            futures.append(executor.submit(concurrent_queue_ops, i))
            futures.append(executor.submit(concurrent_metrics_ops, i))

        for f in futures:
            f.result()

    assert len(errors) == 0, f"并发错误: {errors}"
    print(f"    ✓ 300次并发操作无错误")

    stats = cache.stats()
    print(f"    ✓ 缓存大小: {stats['size']}")

    print("    ✓ 并发安全测试通过")
    return True


# ============================================================
# 9. 性能基准测试
# ============================================================

def test_performance_benchmark():
    """性能基准测试"""
    print("  [9/10] 性能基准...")

    # 缓存写入性能
    cache = AgentResultCache(max_size=10000)
    start = time.time()
    for i in range(10000):
        cache.set(f"agent_{i % 10}", {"task": i}, {"result": i})
    cache_write_time = time.time() - start
    print(f"    ✓ 缓存写入 10K条: {cache_write_time:.3f}s ({10000/cache_write_time:.0f} ops/s)")

    # 缓存读取性能
    start = time.time()
    for i in range(10000):
        cache.get(f"agent_{i % 10}", {"task": i})
    cache_read_time = time.time() - start
    stats = cache.stats()
    print(f"    ✓ 缓存读取 10K次: {cache_read_time:.3f}s ({10000/cache_read_time:.0f} ops/s), 命中率: {stats['hit_rate']}")

    # 消息队列性能
    queue = BoundedMessageQueue(max_size=50000)
    start = time.time()
    for i in range(10000):
        queue.push({"msg": i, "data": "x" * 100})
    queue_push_time = time.time() - start
    print(f"    ✓ 队列推入 10K条: {queue_push_time:.3f}s ({10000/queue_push_time:.0f} ops/s)")

    start = time.time()
    for _ in range(100):
        queue.get_all()
    queue_read_time = time.time() - start
    print(f"    ✓ 队列读取 100次: {queue_read_time:.3f}s ({100/queue_read_time:.0f} ops/s)")

    # 指标记录性能
    metrics = PerformanceMetrics()
    start = time.time()
    for i in range(10000):
        metrics.record("benchmark", i * 0.001)
    metrics_time = time.time() - start
    print(f"    ✓ 指标记录 10K条: {metrics_time:.3f}s ({10000/metrics_time:.0f} ops/s)")

    print("    ✓ 性能基准测试通过")
    return True


# ============================================================
# 10. 优化效果验证测试
# ============================================================

def test_optimization_effectiveness():
    """验证优化效果"""
    print("  [10/10] 优化效果验证...")

    # 1. LLM缓存避免重复创建
    LLMCache.clear()
    llm1 = LLMCache.get("mimo")
    llm2 = LLMCache.get("mimo")
    assert llm1 is llm2
    print("    ✓ LLM缓存: 避免重复实例创建")

    # 2. Agent结果缓存避免重复计算
    cache = AgentResultCache(max_size=100, ttl_seconds=60)
    task = {"contract_text": "测试合同"}
    result = {"score": 85}

    # 模拟首次计算（缓存未命中）
    cached = cache.get("analyzer", task)
    assert cached is None
    cache.set("analyzer", task, result)

    # 模拟后续请求（缓存命中，跳过计算）
    start = time.time()
    for _ in range(1000):
        cache.get("analyzer", task)
    cached_time = time.time() - start
    print(f"    ✓ 结果缓存: 1000次命中耗时{cached_time:.4f}s")

    # 3. 有界队列防止内存溢出
    queue = BoundedMessageQueue(max_size=100)
    for i in range(10000):
        queue.push(f"msg_{i}")
    assert queue.size() <= 100
    print(f"    ✓ 有界队列: 10K消息限制在{queue.size()}条内")

    # 4. 性能监控提供可观测性
    metrics = PerformanceMetrics()
    for i in range(100):
        metrics.record("key_op", 0.01 + (i % 10) * 0.001)
    stats = metrics.get_stats("key_op")
    print(f"    ✓ 性能监控: {stats['count']}次采样, P50={stats['p50']:.3f}s, P99={stats['p99']:.3f}s")

    print("    ✓ 优化效果验证测试通过")
    return True


# ============================================================
# 主测试运行器
# ============================================================

def run_all_tests():
    """运行所有性能优化测试"""
    print("=" * 60)
    print("Day 19: 性能优化测试 - 缓存/限流/监控/基准")
    print("=" * 60)

    tests = [
        ("LLM缓存", test_llm_cache),
        ("Agent结果缓存", test_agent_result_cache),
        ("有界消息队列", test_bounded_message_queue),
        ("性能指标", test_performance_metrics),
        ("性能监控装饰器", test_monitor_decorator),
        ("批量处理器", test_batch_processor),
        ("连接池", test_connection_pool),
        ("并发安全", test_concurrent_safety),
        ("性能基准", test_performance_benchmark),
        ("优化效果验证", test_optimization_effectiveness),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    print("=" * 60)

    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
