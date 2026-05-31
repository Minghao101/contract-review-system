"""
错误处理模块 - 全局错误处理、重试机制、错误分类

功能:
1. 自定义异常层次结构
2. 全局错误处理器
3. 重试机制（指数退避）
4. 错误分类和统计
5. 错误恢复策略
"""
import time
import asyncio
import logging
import traceback
from typing import Any, Callable, Dict, List, Optional, Type
from enum import Enum
from functools import wraps
from datetime import datetime


# ============================================================
# 1. 自定义异常层次结构
# ============================================================

class ContractReviewError(Exception):
    """合同审查系统基础异常"""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN",
        details: Dict[str, Any] = None,
        recoverable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.recoverable = recoverable
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp
        }


class DocumentParseError(ContractReviewError):
    """文档解析错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message,
            error_code="DOC_PARSE_ERROR",
            details=details,
            recoverable=False
        )


class LLMError(ContractReviewError):
    """LLM调用错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message,
            error_code="LLM_ERROR",
            details=details,
            recoverable=True  # LLM错误可重试
        )


class AgentError(ContractReviewError):
    """Agent处理错误"""

    def __init__(self, message: str, agent_id: str = None, details: Dict[str, Any] = None):
        details = details or {}
        if agent_id:
            details["agent_id"] = agent_id
        super().__init__(
            message,
            error_code="AGENT_ERROR",
            details=details,
            recoverable=True
        )


class ValidationError(ContractReviewError):
    """输入验证错误"""

    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details=details,
            recoverable=False
        )


class TimeoutError(ContractReviewError):
    """超时错误"""

    def __init__(self, message: str, timeout: float = None, details: Dict[str, Any] = None):
        details = details or {}
        if timeout:
            details["timeout"] = timeout
        super().__init__(
            message,
            error_code="TIMEOUT_ERROR",
            details=details,
            recoverable=True
        )


class MemoryError(ContractReviewError):
    """记忆系统错误"""

    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message,
            error_code="MEMORY_ERROR",
            details=details,
            recoverable=True
        )


class WorkflowError(ContractReviewError):
    """工作流错误"""

    def __init__(self, message: str, step: str = None, details: Dict[str, Any] = None):
        details = details or {}
        if step:
            details["step"] = step
        super().__init__(
            message,
            error_code="WORKFLOW_ERROR",
            details=details,
            recoverable=True
        )


# ============================================================
# 2. 错误分类器
# ============================================================

class ErrorCategory(str, Enum):
    """错误分类"""
    TRANSIENT = "transient"       # 临时错误（可重试）
    PERSISTENT = "persistent"     # 持久错误（不可重试）
    FATAL = "fatal"               # 致命错误（系统异常）
    USER_INPUT = "user_input"     # 用户输入错误


class ErrorClassifier:
    """错误分类器 - 自动判断错误类型和恢复策略"""

    # 可重试的异常类型
    RETRYABLE_ERRORS = (
        ConnectionError,
        TimeoutError,
        LLMError,
    )

    # 不可重试的异常类型
    NON_RETRYABLE_ERRORS = (
        DocumentParseError,
        ValidationError,
    )

    @classmethod
    def classify(cls, error: Exception) -> ErrorCategory:
        """分类错误"""
        if isinstance(error, cls.NON_RETRYABLE_ERRORS):
            return ErrorCategory.PERSISTENT
        if isinstance(error, cls.RETRYABLE_ERRORS):
            return ErrorCategory.TRANSIENT
        if isinstance(error, ContractReviewError):
            if error.recoverable:
                return ErrorCategory.TRANSIENT
            return ErrorCategory.PERSISTENT
        if isinstance(error, (MemoryError, SystemError)):
            return ErrorCategory.FATAL
        # 未知异常默认可重试
        return ErrorCategory.TRANSIENT

    @classmethod
    def should_retry(cls, error: Exception) -> bool:
        """判断是否应该重试"""
        return cls.classify(error) == ErrorCategory.TRANSIENT

    @classmethod
    def get_max_retries(cls, error: Exception) -> int:
        """获取最大重试次数"""
        category = cls.classify(error)
        if category == ErrorCategory.TRANSIENT:
            return 3
        return 0


# ============================================================
# 3. 重试机制（指数退避）
# ============================================================

class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """获取第N次重试的延迟时间"""
        import random
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay


def retry(
    config: RetryConfig = None,
    retryable_exceptions: tuple = None,
    on_retry: Callable = None
):
    """
    重试装饰器

    Usage:
        @retry(config=RetryConfig(max_retries=3))
        async def call_llm():
            ...
    """
    if config is None:
        config = RetryConfig()

    if retryable_exceptions is None:
        retryable_exceptions = (Exception,)

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt >= config.max_retries:
                        break

                    delay = config.get_delay(attempt)

                    if on_retry:
                        on_retry(attempt + 1, delay, e)

                    logger.warning(
                        f"重试 {attempt + 1}/{config.max_retries}: "
                        f"{func.__name__} 失败({type(e).__name__}: {e}), "
                        f"等待 {delay:.1f}s"
                    )

                    await asyncio.sleep(delay)

            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt >= config.max_retries:
                        break

                    delay = config.get_delay(attempt)

                    if on_retry:
                        on_retry(attempt + 1, delay, e)

                    logger.warning(
                        f"重试 {attempt + 1}/{config.max_retries}: "
                        f"{func.__name__} 失败({type(e).__name__}: {e}), "
                        f"等待 {delay:.1f}s"
                    )

                    time.sleep(delay)

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================
# 4. 全局错误处理器
# ============================================================

class GlobalErrorHandler:
    """
    全局错误处理器

    - 统一错误格式
    - 错误统计
    - 错误恢复策略
    """

    def __init__(self):
        self._error_counts: Dict[str, int] = {}
        self._error_history: List[Dict[str, Any]] = []
        self._max_history = 1000

    def handle(
        self,
        error: Exception,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        处理异常，返回统一错误格式

        Args:
            error: 异常对象
            context: 错误上下文

        Returns:
            统一错误字典
        """
        # 分类
        category = ErrorClassifier.classify(error)

        # 统计
        error_type = type(error).__name__
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        # 记录历史
        error_record = {
            "error_type": error_type,
            "error_code": getattr(error, "error_code", "UNKNOWN"),
            "message": str(error),
            "category": category.value,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
            "traceback": traceback.format_exc()
        }
        self._error_history.append(error_record)
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]

        # 日志
        if category == ErrorCategory.FATAL:
            logger.critical(f"致命错误: {error}", exc_info=True)
        elif category == ErrorCategory.TRANSIENT:
            logger.warning(f"临时错误: {error}")
        else:
            logger.error(f"错误: {error}")

        # 构建响应
        if isinstance(error, ContractReviewError):
            result = error.to_dict()
        else:
            result = {
                "error": True,
                "error_code": "UNKNOWN",
                "message": str(error),
                "details": context or {},
                "recoverable": ErrorClassifier.should_retry(error),
                "timestamp": datetime.now().isoformat()
            }

        result["category"] = category.value
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        return {
            "total_errors": sum(self._error_counts.values()),
            "by_type": dict(self._error_counts),
            "recent_count": len(self._error_history)
        }

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误历史"""
        return self._error_history[-limit:]

    def clear(self):
        """清空统计"""
        self._error_counts.clear()
        self._error_history.clear()


# 全局错误处理器实例
error_handler = GlobalErrorHandler()


# ============================================================
# 5. 安全执行器
# ============================================================

class SafeExecutor:
    """
    安全执行器 - 包装函数调用，捕获异常并返回统一结果
    """

    @staticmethod
    async def execute(
        func: Callable,
        *args,
        error_context: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        安全执行异步函数

        Args:
            func: 要执行的异步函数
            error_context: 错误上下文

        Returns:
            {"success": True, "result": ...} 或 {"success": False, "error": ...}
        """
        try:
            result = await func(*args, **kwargs)
            return {"success": True, "result": result}
        except Exception as e:
            error_result = error_handler.handle(e, error_context)
            return {"success": False, "error": error_result}

    @staticmethod
    def execute_sync(
        func: Callable,
        *args,
        error_context: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        安全执行同步函数
        """
        try:
            result = func(*args, **kwargs)
            return {"success": True, "result": result}
        except Exception as e:
            error_result = error_handler.handle(e, error_context)
            return {"success": False, "error": error_result}


# ============================================================
# 6. 输入验证器
# ============================================================

class InputValidator:
    """输入验证工具"""

    @staticmethod
    def validate_contract_text(text: str) -> None:
        """验证合同文本"""
        if not text:
            raise ValidationError("合同文本为空", field="contract_text")
        if not isinstance(text, str):
            raise ValidationError("合同文本必须是字符串", field="contract_text")
        if len(text.strip()) < 10:
            raise ValidationError("合同文本过短（至少10个字符）", field="contract_text")

    @staticmethod
    def validate_contract_type(contract_type: str) -> None:
        """验证合同类型"""
        valid_types = ["general", "service", "purchase", "lease", "employment", "nda", "license"]
        if contract_type and contract_type not in valid_types:
            raise ValidationError(
                f"无效的合同类型: {contract_type}",
                field="contract_type",
                details={"valid_types": valid_types}
            )

    @staticmethod
    def validate_task_id(task_id: str) -> None:
        """验证任务ID"""
        if not task_id:
            raise ValidationError("任务ID为空", field="task_id")
        if not isinstance(task_id, str):
            raise ValidationError("任务ID必须是字符串", field="task_id")

    @staticmethod
    def validate_agent_input(task: Dict[str, Any], required_fields: List[str]) -> None:
        """验证Agent输入"""
        for field in required_fields:
            if field not in task:
                raise ValidationError(
                    f"缺少必填字段: {field}",
                    field=field,
                    details={"required_fields": required_fields}
                )


# ============================================================
# 日志配置
# ============================================================

logger = logging.getLogger("contract_review")
logger.setLevel(logging.DEBUG)

# 避免重复添加handler
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
