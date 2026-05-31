"""
Day 17: 记忆系统测试 - 并发性能、通知机制、上下文压缩、存储优化
"""
import sys
import time
import asyncio
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.memory.memory_layer import MemoryLayer
from src.memory.private_memory import AgentPrivateMemory
from src.memory.shared_memory import SharedMemoryManager, MemoryEntry


# ============================================================
# 1. 共享记忆并发性能测试
# ============================================================

def test_concurrent_read_write():
    """多线程并发读写"""
    print("  [1/8] 多线程并发读写...")

    memory = SharedMemoryManager(contract_id="concurrent_test")
    errors = []
    write_count = [0]
    read_count = [0]
    lock = threading.Lock()

    def writer(agent_id, index):
        try:
            for i in range(10):
                memory.write(
                    agent_id=agent_id,
                    key=f"key_{index}_{i}",
                    value={"thread": index, "seq": i, "data": "x" * 100},
                    layer=MemoryLayer.ANALYSIS
                )
                with lock:
                    write_count[0] += 1
        except Exception as e:
            errors.append(f"Writer {index}: {e}")

    def reader(agent_id, index):
        try:
            for i in range(10):
                value = memory.read(
                    agent_id=agent_id,
                    key=f"key_{index}_{i}",
                    layer=MemoryLayer.ANALYSIS
                )
                with lock:
                    read_count[0] += 1
        except Exception as e:
            errors.append(f"Reader {index}: {e}")

    start = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(5):
            futures.append(executor.submit(writer, f"agent_w{i}", i))
            futures.append(executor.submit(reader, f"agent_r{i}", i))
        for f in as_completed(futures):
            f.result()
    elapsed = time.time() - start

    assert len(errors) == 0, f"并发错误: {errors}"
    print(f"    ✓ 写入次数: {write_count[0]}")
    print(f"    ✓ 读取次数: {read_count[0]}")
    print(f"    ✓ 并发耗时: {elapsed:.3f}秒")
    print(f"    ✓ 吞吐量: {(write_count[0] + read_count[0]) / elapsed:.0f} ops/s")
    print("    ✓ 多线程并发读写测试通过")
    return True


def test_concurrent_write_performance():
    """大量写入性能测试"""
    print("  [2/8] 大量写入性能测试...")

    memory = SharedMemoryManager(contract_id="perf_test")
    n_writes = 1000

    start = time.time()
    for i in range(n_writes):
        memory.write(
            agent_id="perf_agent",
            key=f"item_{i}",
            value={"index": i, "data": "x" * 50},
            layer=MemoryLayer.ANALYSIS
        )
    elapsed = time.time() - start

    # 验证所有数据可读
    read_start = time.time()
    for i in range(n_writes):
        value = memory.read(agent_id="reader", key=f"item_{i}", layer=MemoryLayer.ANALYSIS)
        assert value is not None
    read_elapsed = time.time() - read_start

    stats = memory.get_stats()
    print(f"    ✓ 写入 {n_writes} 条: {elapsed:.3f}秒 ({n_writes / elapsed:.0f} writes/s)")
    print(f"    ✓ 读取 {n_writes} 条: {read_elapsed:.3f}秒 ({n_writes / read_elapsed:.0f} reads/s)")
    print(f"    ✓ 总记忆数: {stats['analysis_count']}")

    # 导出大小测试
    export_start = time.time()
    exported = memory.export_all()
    export_elapsed = time.time() - export_start
    print(f"    ✓ 导出耗时: {export_elapsed:.3f}秒")

    print("    ✓ 大量写入性能测试通过")
    return True


# ============================================================
# 2. 记忆通知机制测试
# ============================================================

def test_notification_performance():
    """通知机制性能测试"""
    print("  [3/8] 通知机制性能测试...")

    memory = SharedMemoryManager(contract_id="notify_perf")
    notification_count = [0]

    def counter(key, agent_id, value):
        notification_count[0] += 1

    # 订阅多个key
    for i in range(10):
        memory.subscribe(f"key_{i}", counter)

    start = time.time()
    # 写入触发通知
    for i in range(100):
        memory.write(
            agent_id="notifier",
            key=f"key_{i % 10}",
            value=f"value_{i}",
            layer=MemoryLayer.ANALYSIS
        )
    elapsed = time.time() - start

    assert notification_count[0] == 100
    print(f"    ✓ 100次通知触发: {elapsed:.3f}秒")
    throughput = 100 / elapsed if elapsed > 0 else float('inf')
    print(f"    ✓ 通知吞吐量: {throughput:.0f} notifications/s")

    # 清理订阅
    for i in range(10):
        memory.unsubscribe(f"key_{i}", counter)

    print("    ✓ 通知机制性能测试通过")
    return True


def test_multi_subscriber_notification():
    """多订阅者通知"""
    print("  [4/8] 多订阅者通知...")

    memory = SharedMemoryManager(contract_id="multi_sub")
    results = {"a": [], "b": [], "c": []}

    def make_callback(name):
        def cb(key, agent_id, value):
            results[name].append({"key": key, "agent_id": agent_id, "value": value})
        return cb

    # 3个订阅者订阅同一个key（保留引用以便取消订阅）
    cb_a = make_callback("a")
    cb_b = make_callback("b")
    cb_c = make_callback("c")
    memory.subscribe("shared_key", cb_a)
    memory.subscribe("shared_key", cb_b)
    memory.subscribe("shared_key", cb_c)

    # 写入
    memory.write(
        agent_id="writer",
        key="shared_key",
        value="test_value",
        layer=MemoryLayer.CONTEXT
    )

    # 验证3个订阅者都收到通知
    assert len(results["a"]) == 1
    assert len(results["b"]) == 1
    assert len(results["c"]) == 1
    print("    ✓ 3个订阅者都收到通知")

    # 取消一个（使用原始引用）
    memory.unsubscribe("shared_key", cb_b)
    memory.write(
        agent_id="writer",
        key="shared_key",
        value="test_value_2",
        layer=MemoryLayer.CONTEXT
    )

    assert len(results["a"]) == 2
    assert len(results["b"]) == 1  # 不再收到
    assert len(results["c"]) == 2
    print("    ✓ 取消订阅后不再收到通知")

    # 清理
    memory.unsubscribe("shared_key", cb_a)
    memory.unsubscribe("shared_key", cb_c)

    print("    ✓ 多订阅者通知测试通过")
    return True


# ============================================================
# 3. 上下文压缩测试
# ============================================================

def test_context_compression_threshold():
    """上下文压缩阈值测试"""
    print("  [5/8] 上下文压缩阈值...")

    # 测试不同max_context_length
    for max_len in [5, 10, 20]:
        memory = AgentPrivateMemory(agent_id=f"compress_{max_len}", max_context_length=max_len)

        # 填充到80%
        fill_count = int(max_len * 0.7)
        for i in range(fill_count):
            memory.update_context("user", f"question_{i}")

        # 此时不应压缩
        summary = memory.compress_context()
        assert summary == "", f"max_len={max_len}时70%不应压缩"

        # 填充超过80%
        while len(memory.get_context()) < max_len * 0.85:
            memory.update_context("assistant", f"answer_{len(memory.get_context())}")

        # 此时应压缩
        summary = memory.compress_context()
        assert summary != "", f"max_len={max_len}时85%应压缩"
        print(f"    ✓ max_len={max_len}: 压缩成功")

    print("    ✓ 上下文压缩阈值测试通过")
    return True


def test_context_compression_preserves_recent():
    """上下文压缩保留最近内容"""
    print("  [6/8] 上下文压缩保留最近内容...")

    memory = AgentPrivateMemory(agent_id="preserve_test", max_context_length=10)

    # 添加大量对话
    for i in range(20):
        memory.update_context("user", f"question_{i}")
        memory.update_context("assistant", f"answer_{i}")

    # 压缩
    summary = memory.compress_context()
    assert summary != ""

    # 验证最近的对话保留
    full = memory.get_full_context()
    recent = full.get("recent_context", [])
    assert len(recent) > 0

    # 最近的内容应该包含后面的问题
    last_user_msg = None
    for ctx in reversed(recent):
        if ctx.get("role") == "user":
            last_user_msg = ctx.get("content", "")
            break

    assert last_user_msg is not None
    print(f"    ✓ 摘要长度: {len(summary)} 字符")
    print(f"    ✓ 保留最近 {len(recent)} 条上下文")
    print(f"    ✓ 最近用户消息: {last_user_msg[:30]}...")

    print("    ✓ 上下文压缩保留最近内容测试通过")
    return True


# ============================================================
# 4. 记忆存储优化测试
# ============================================================

def test_memory_entry_versioning():
    """记忆版本控制"""
    print("  [7/8] 记忆版本控制...")

    memory = SharedMemoryManager(contract_id="version_test")

    # 写入初始版本
    v1 = memory.write(
        agent_id="agent_1",
        key="doc_info",
        value={"version": 1},
        layer=MemoryLayer.CONTEXT
    )
    assert v1 == 1

    # 写入同一key
    v2 = memory.write(
        agent_id="agent_1",
        key="doc_info",
        value={"version": 2},
        layer=MemoryLayer.CONTEXT
    )
    assert v2 == 2

    # 写入不同agent
    v3 = memory.write(
        agent_id="agent_2",
        key="doc_info",
        value={"version": 3, "updated_by": "agent_2"},
        layer=MemoryLayer.CONTEXT
    )
    assert v3 == 3

    # 读取最新版本
    value = memory.read(agent_id="reader", key="doc_info", layer=MemoryLayer.CONTEXT)
    assert value["version"] == 3
    print(f"    ✓ 版本递增: v{v1} -> v{v2} -> v{v3}")
    print(f"    ✓ 最新值: {value}")

    print("    ✓ 记忆版本控制测试通过")
    return True


def test_memory_export_import():
    """记忆导出导入（持久化模拟）"""
    print("  [8/8] 记忆导出导入...")

    # 写入数据
    memory = SharedMemoryManager(contract_id="export_test")
    memory.write(agent_id="agent_1", key="k1", value="v1", layer=MemoryLayer.CONTEXT)
    memory.write(agent_id="agent_2", key="k2", value={"nested": True}, layer=MemoryLayer.ANALYSIS)
    memory.write(agent_id="agent_3", key="k3", value=42, layer=MemoryLayer.DECISION)

    # 导出
    exported = memory.export_all()
    assert "context" in exported
    assert "analysis" in exported
    assert "decision" in exported

    # 验证导出结构
    ctx_export = exported["context"]
    assert "k1" in ctx_export
    assert ctx_export["k1"]["value"] == "v1"
    print(f"    ✓ 导出3层数据: {list(exported.keys())}")
    print(f"    ✓ CONTEXT层: {list(ctx_export.keys())}")

    # 验证MemoryEntry结构
    entry_data = ctx_export["k1"]
    assert "agent_id" in entry_data
    assert "key" in entry_data
    assert "value" in entry_data
    assert "layer" in entry_data
    assert "version" in entry_data
    print(f"    ✓ MemoryEntry结构完整: {list(entry_data.keys())}")

    # 模拟导入（新建manager并写入）
    imported_memory = SharedMemoryManager(contract_id="import_test")
    for layer_name, layer_data in exported.items():
        for key, entry_dict in layer_data.items():
            imported_memory.write(
                agent_id=entry_dict["agent_id"],
                key=key,
                value=entry_dict["value"],
                layer=MemoryLayer(layer_name)
            )

    # 验证导入数据
    v = imported_memory.read(agent_id="reader", key="k1", layer=MemoryLayer.CONTEXT)
    assert v == "v1"
    v = imported_memory.read(agent_id="reader", key="k2", layer=MemoryLayer.ANALYSIS)
    assert v == {"nested": True}
    print("    ✓ 导入数据验证通过")

    print("    ✓ 记忆导出导入测试通过")
    return True


# ============================================================
# 主测试运行器
# ============================================================

def run_all_tests():
    """运行所有Day 17记忆系统测试"""
    print("=" * 60)
    print("Day 17: 记忆系统测试 - 并发/通知/压缩/存储")
    print("=" * 60)

    tests = [
        ("多线程并发读写", test_concurrent_read_write),
        ("大量写入性能", test_concurrent_write_performance),
        ("通知机制性能", test_notification_performance),
        ("多订阅者通知", test_multi_subscriber_notification),
        ("上下文压缩阈值", test_context_compression_threshold),
        ("压缩保留最近内容", test_context_compression_preserves_recent),
        ("记忆版本控制", test_memory_entry_versioning),
        ("记忆导出导入", test_memory_export_import),
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
