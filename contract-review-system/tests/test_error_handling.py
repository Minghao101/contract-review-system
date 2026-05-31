"""
Day 20: 错误处理完善测试
测试异常层次、重试机制、全局错误处理、输入验证
"""
import sys
import time
import asyncio
import logging
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.error_handling import (
    # 异常类
    ContractReviewError,
    DocumentParseError,
    LLMError,
    AgentError,
    ValidationError,
    TimeoutError,
    MemoryError,
    WorkflowError,
    # 工具类
    ErrorCategory,
    ErrorClassifier,
    RetryConfig,
    retry,
    GlobalErrorHandler,
    error_handler,
    SafeExecutor,
    InputValidator,
    logger,
)


# ============================================================
# 1. 异常层次结构测试
# ============================================================

def test_exception_hierarchy():
    """测试自定义异常层次结构"""
    print("  [1/10] 异常层次结构...")

    # ContractReviewError 基础异常
    err = ContractReviewError("基础错误", error_code="TEST")
    assert str(err) == "基础错误"
    assert err.error_code == "TEST"
    assert err.recoverable is True
    print("    ✓ ContractReviewError 基础异常")

    # DocumentParseError
    err = DocumentParseError("解析失败")
    assert err.error_code == "DOC_PARSE_ERROR"
    assert err.recoverable is False
    assert isinstance(err, ContractReviewError)
    print("    ✓ DocumentParseError (不可恢复)")

    # LLMError
    err = LLMError("LLM超时")
    assert err.error_code == "LLM_ERROR"
    assert err.recoverable is True
    print("    ✓ LLMError (可恢复)")

    # AgentError
    err = AgentError("Agent处理失败", agent_id="parser_01")
    assert err.error_code == "AGENT_ERROR"
    assert err.details["agent_id"] == "parser_01"
    print("    ✓ AgentError (含agent_id)")

    # ValidationError
    err = ValidationError("字段为空", field="contract_text")
    assert err.error_code == "VALIDATION_ERROR"
    assert err.details["field"] == "contract_text"
    assert err.recoverable is False
    print("    ✓ ValidationError (含field)")

    # TimeoutError
    err = TimeoutError("请求超时", timeout=30.0)
    assert err.error_code == "TIMEOUT_ERROR"
    assert err.details["timeout"] == 30.0
    print("    ✓ TimeoutError (含timeout)")

    # MemoryError
    err = MemoryError("记忆存储失败")
    assert err.error_code == "MEMORY_ERROR"
    print("    ✓ MemoryError")

    # WorkflowError
    err = WorkflowError("工作流中断", step="analyze_clauses")
    assert err.error_code == "WORKFLOW_ERROR"
    assert err.details["step"] == "analyze_clauses"
    print("    ✓ WorkflowError (含step)")

    # to_dict
    err = ContractReviewError("测试", error_code="DICT_TEST", details={"key": "value"})
    d = err.to_dict()
    assert d["error"] is True
    assert d["error_code"] == "DICT_TEST"
    assert d["details"]["key"] == "value"
    assert "timestamp" in d
    print("    ✓ to_dict 序列化正确")

    print("    ✓ 异常层次结构测试通过")
    return True


# ============================================================
# 2. 错误分类器测试
# ============================================================

def test_error_classifier():
    """测试错误分类器"""
    print("  [2/10] 错误分类器...")

    # LLMError → TRANSIENT (可重试)
    cat = ErrorClassifier.classify(LLMError("超时"))
    assert cat == ErrorCategory.TRANSIENT
    assert ErrorClassifier.should_retry(LLMError("超时")) is True
    print("    ✓ LLMError → TRANSIENT (可重试)")

    # DocumentParseError → PERSISTENT (不可重试)
    cat = ErrorClassifier.classify(DocumentParseError("格式错误"))
    assert cat == ErrorCategory.PERSISTENT
    assert ErrorClassifier.should_retry(DocumentParseError("格式错误")) is False
    print("    ✓ DocumentParseError → PERSISTENT (不可重试)")

    # ValidationError → PERSISTENT
    cat = ErrorClassifier.classify(ValidationError("字段为空"))
    assert cat == ErrorCategory.PERSISTENT
    print("    ✓ ValidationError → PERSISTENT")

    # ConnectionError → TRANSIENT
    cat = ErrorClassifier.classify(ConnectionError("连接失败"))
    assert cat == ErrorCategory.TRANSIENT
    print("    ✓ ConnectionError → TRANSIENT")

    # 未知异常 → TRANSIENT
    cat = ErrorClassifier.classify(ValueError("未知"))
    assert cat == ErrorCategory.TRANSIENT
    print("    ✓ 未知异常 → TRANSIENT")

    # 最大重试次数
    assert ErrorClassifier.get_max_retries(LLMError("超时")) == 3
    assert ErrorClassifier.get_max_retries(DocumentParseError("格式错误")) == 0
    print("    ✓ 最大重试次数正确")

    print("    ✓ 错误分类器测试通过")
    return True


# ============================================================
# 3. 重试机制测试（同步）
# ============================================================

def test_retry_sync():
    """测试同步重试机制"""
    print("  [3/10] 同步重试...")

    call_count = [0]

    @retry(config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False))
    def flaky_function():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ConnectionError("连接失败")
        return "success"

    result = flaky_function()
    assert result == "success"
    assert call_count[0] == 3
    print(f"    ✓ 第3次成功, 总调用{call_count[0]}次")

    # 全部失败
    call_count2 = [0]

    @retry(config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False))
    def always_fail():
        call_count2[0] += 1
        raise ConnectionError("始终失败")

    try:
        always_fail()
        assert False, "应该抛出异常"
    except ConnectionError:
        assert call_count2[0] == 3  # 1次初始 + 2次重试
        print(f"    ✓ 全部失败后抛出异常, 总调用{call_count2[0]}次")

    print("    ✓ 同步重试测试通过")
    return True


# ============================================================
# 4. 重试机制测试（异步）
# ============================================================

def test_retry_async():
    """测试异步重试机制"""
    print("  [4/10] 异步重试...")

    call_count = [0]

    @retry(config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False))
    async def async_flaky():
        call_count[0] += 1
        if call_count[0] < 3:
            raise LLMError("LLM暂时不可用")
        return "async_success"

    result = asyncio.run(async_flaky())
    assert result == "async_success"
    assert call_count[0] == 3
    print(f"    ✓ 异步第3次成功, 总调用{call_count[0]}次")

    # on_retry回调
    retry_log = []

    def on_retry(attempt, delay, error):
        retry_log.append({"attempt": attempt, "delay": delay, "error": str(error)})

    call_count3 = [0]

    @retry(
        config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False),
        on_retry=on_retry
    )
    async def async_with_callback():
        call_count3[0] += 1
        if call_count3[0] < 3:
            raise LLMError("回调测试")
        return "callback_done"

    result = asyncio.run(async_with_callback())
    assert result == "callback_done"
    assert len(retry_log) == 2
    assert retry_log[0]["attempt"] == 1
    print(f"    ✓ on_retry回调触发{len(retry_log)}次")

    print("    ✓ 异步重试测试通过")
    return True


# ============================================================
# 5. 全局错误处理器测试
# ============================================================

def test_global_error_handler():
    """测试全局错误处理器"""
    print("  [5/10] 全局错误处理器...")

    handler = GlobalErrorHandler()

    # 处理 ContractReviewError
    result = handler.handle(
        LLMError("LLM调用失败", details={"model": "mimo"}),
        context={"task_id": "task_001"}
    )
    assert result["error"] is True
    assert result["error_code"] == "LLM_ERROR"
    assert result["category"] == "transient"
    assert result["recoverable"] is True
    print("    ✓ LLMError 处理正确")

    # 处理普通异常
    result = handler.handle(ValueError("普通错误"))
    assert result["error"] is True
    assert result["error_code"] == "UNKNOWN"
    print("    ✓ 普通异常处理正确")

    # 处理 ValidationError
    result = handler.handle(ValidationError("字段缺失", field="name"))
    assert result["category"] == "persistent"
    assert result["recoverable"] is False
    print("    ✓ ValidationError 处理正确")

    # 统计
    stats = handler.get_stats()
    assert stats["total_errors"] == 3
    assert "LLMError" in stats["by_type"]
    assert "ValueError" in stats["by_type"]
    print(f"    ✓ 错误统计: {stats['total_errors']}次")

    # 历史
    history = handler.get_history(limit=2)
    assert len(history) == 2
    assert history[-1]["error_type"] == "ValidationError"
    print(f"    ✓ 错误历史: 最近{len(history)}条")

    # 清空
    handler.clear()
    assert handler.get_stats()["total_errors"] == 0
    print("    ✓ 统计清空成功")

    print("    ✓ 全局错误处理器测试通过")
    return True


# ============================================================
# 6. 安全执行器测试
# ============================================================

def test_safe_executor():
    """测试安全执行器"""
    print("  [6/10] 安全执行器...")

    # 成功执行（异步）
    async def success_func():
        return 42

    result = asyncio.run(SafeExecutor.execute(success_func))
    assert result["success"] is True
    assert result["result"] == 42
    print("    ✓ 异步成功执行")

    # 失败执行（异步）
    async def fail_func():
        raise LLMError("测试失败")

    result = asyncio.run(SafeExecutor.execute(
        fail_func,
        error_context={"task": "test"}
    ))
    assert result["success"] is False
    assert result["error"]["error_code"] == "LLM_ERROR"
    print("    ✓ 异步失败执行（统一错误格式）")

    # 成功执行（同步）
    def sync_success():
        return "sync_ok"

    result = SafeExecutor.execute_sync(sync_success)
    assert result["success"] is True
    assert result["result"] == "sync_ok"
    print("    ✓ 同步成功执行")

    # 失败执行（同步）
    def sync_fail():
        raise ValidationError("同步验证失败")

    result = SafeExecutor.execute_sync(sync_fail)
    assert result["success"] is False
    assert result["error"]["error_code"] == "VALIDATION_ERROR"
    print("    ✓ 同步失败执行")

    print("    ✓ 安全执行器测试通过")
    return True


# ============================================================
# 7. 输入验证器测试
# ============================================================

def test_input_validator():
    """测试输入验证器"""
    print("  [7/10] 输入验证器...")

    # 正常合同文本
    InputValidator.validate_contract_text("这是一个正常的合同文本，包含足够的内容来进行验证。")
    print("    ✓ 正常合同文本验证通过")

    # 空文本
    try:
        InputValidator.validate_contract_text("")
        assert False, "应该抛出异常"
    except ValidationError as e:
        assert e.error_code == "VALIDATION_ERROR"
        assert e.details["field"] == "contract_text"
        print("    ✓ 空文本抛出ValidationError")

    # 过短文本
    try:
        InputValidator.validate_contract_text("短")
        assert False, "应该抛出异常"
    except ValidationError:
        print("    ✓ 过短文本抛出ValidationError")

    # 无效合同类型
    try:
        InputValidator.validate_contract_type("invalid_type")
        assert False, "应该抛出异常"
    except ValidationError as e:
        assert "valid_types" in e.details
        print("    ✓ 无效合同类型抛出ValidationError")

    # 有效合同类型
    InputValidator.validate_contract_type("service")
    print("    ✓ 有效合同类型验证通过")

    # 空合同类型（允许）
    InputValidator.validate_contract_type("")
    print("    ✓ 空合同类型允许")

    # 任务ID验证
    InputValidator.validate_task_id("task_001")
    print("    ✓ 有效任务ID验证通过")

    try:
        InputValidator.validate_task_id("")
        assert False, "应该抛出异常"
    except ValidationError:
        print("    ✓ 空任务ID抛出ValidationError")

    # Agent输入验证
    task = {"contract_text": "合同内容", "type": "service"}
    InputValidator.validate_agent_input(task, ["contract_text", "type"])
    print("    ✓ Agent输入验证通过")

    try:
        InputValidator.validate_agent_input({}, ["contract_text"])
        assert False, "应该抛出异常"
    except ValidationError as e:
        assert e.details["field"] == "contract_text"
        print("    ✓ 缺少字段抛出ValidationError")

    print("    ✓ 输入验证器测试通过")
    return True


# ============================================================
# 8. 错误恢复策略测试
# ============================================================

def test_error_recovery():
    """测试错误恢复策略"""
    print("  [8/10] 错误恢复策略...")

    # 可恢复错误：重试后成功
    recovery_log = []

    @retry(config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False))
    async def recoverable_operation():
        attempt = len(recovery_log) + 1
        recovery_log.append(attempt)
        if attempt < 3:
            raise LLMError("临时不可用")
        return "recovered"

    result = asyncio.run(recoverable_operation())
    assert result == "recovered"
    print(f"    ✓ 可恢复错误: 重试{len(recovery_log)}次后成功")

    # 不可恢复错误：直接失败
    try:
        @retry(
            config=RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ConnectionError,)
        )
        def non_recoverable():
            raise ValidationError("不可重试")

        non_recoverable()
        assert False, "应该抛出异常"
    except ValidationError:
        print("    ✓ 不可恢复错误: 直接失败（不重试）")

    # 混合错误类型
    call_count = [0]

    @retry(
        config=RetryConfig(max_retries=5, base_delay=0.01, jitter=False),
        retryable_exceptions=(ConnectionError, LLMError)
    )
    async def mixed_errors():
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError("连接失败")
        elif call_count[0] == 2:
            raise LLMError("LLM失败")
        return "mixed_ok"

    result = asyncio.run(mixed_errors())
    assert result == "mixed_ok"
    assert call_count[0] == 3
    print(f"    ✓ 混合错误恢复: {call_count[0]}次调用后成功")

    print("    ✓ 错误恢复策略测试通过")
    return True


# ============================================================
# 9. 日志记录测试
# ============================================================

def test_logging():
    """测试日志记录"""
    print("  [9/10] 日志记录...")

    # logger存在
    assert logger is not None
    assert logger.name == "contract_review"
    print("    ✓ logger实例存在")

    # 日志级别
    assert logger.level <= logging.DEBUG
    print(f"    ✓ 日志级别: {logging.getLevelName(logger.level)}")

    # 记录不同级别
    logger.debug("Debug测试消息")
    logger.info("Info测试消息")
    logger.warning("Warning测试消息")
    logger.error("Error测试消息")
    print("    ✓ 四个级别日志均可记录")

    # 错误处理中的日志
    handler = GlobalErrorHandler()
    handler.handle(LLMError("日志测试"))
    handler.handle(DocumentParseError("日志测试2"))
    print("    ✓ 错误处理自动记录日志")

    print("    ✓ 日志记录测试通过")
    return True


# ============================================================
# 10. 端到端错误处理测试
# ============================================================

def test_end_to_end_error_handling():
    """端到端错误处理测试"""
    print("  [10/10] 端到端错误处理...")

    # 模拟完整的错误处理流程
    handler = GlobalErrorHandler()

    # 1. 输入验证
    try:
        InputValidator.validate_contract_text("")
    except ValidationError as e:
        result = handler.handle(e, {"step": "input_validation"})
        assert result["error"] is True
        assert result["category"] == "persistent"
        print("    ✓ 步骤1: 输入验证错误处理")

    # 2. LLM调用失败（可恢复）
    @retry(config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False))
    async def mock_llm_call():
        raise LLMError("模型暂时不可用")

    try:
        asyncio.run(mock_llm_call())
    except LLMError as e:
        result = handler.handle(e, {"step": "llm_call", "model": "mimo"})
        assert result["recoverable"] is True
        assert result["category"] == "transient"
        print("    ✓ 步骤2: LLM调用错误处理")

    # 3. Agent处理失败
    try:
        raise AgentError("条款分析失败", agent_id="clause_analyst")
    except AgentError as e:
        result = handler.handle(e, {"step": "agent_process"})
        assert result["error_code"] == "AGENT_ERROR"
        print("    ✓ 步骤3: Agent错误处理")

    # 4. 工作流错误
    try:
        raise WorkflowError("工作流中断", step="check_compliance")
    except WorkflowError as e:
        result = handler.handle(e, {"step": "workflow"})
        assert result["details"]["step"] == "check_compliance"
        print("    ✓ 步骤4: 工作流错误处理")

    # 汇总统计
    stats = handler.get_stats()
    assert stats["total_errors"] == 4
    print(f"    ✓ 总错误统计: {stats['total_errors']}次, 类型分布: {stats['by_type']}")

    print("    ✓ 端到端错误处理测试通过")
    return True


# ============================================================
# 主测试运行器
# ============================================================

def run_all_tests():
    """运行所有错误处理测试"""
    print("=" * 60)
    print("Day 20: 错误处理完善测试 - 异常/重试/验证/恢复")
    print("=" * 60)

    tests = [
        ("异常层次结构", test_exception_hierarchy),
        ("错误分类器", test_error_classifier),
        ("同步重试", test_retry_sync),
        ("异步重试", test_retry_async),
        ("全局错误处理器", test_global_error_handler),
        ("安全执行器", test_safe_executor),
        ("输入验证器", test_input_validator),
        ("错误恢复策略", test_error_recovery),
        ("日志记录", test_logging),
        ("端到端错误处理", test_end_to_end_error_handling),
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
