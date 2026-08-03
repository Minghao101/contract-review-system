"""
合规检查Agent模块 - 使用 LangChain 高级抽象（ChatPromptTemplate + structured output）
"""
from typing import Any, Dict, List, Optional
import logging

from langchain_core.prompts import ChatPromptTemplate

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .schemas import ComplianceCheckResult
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class ComplianceCheckerAgent(BaseAgent):
    """
    合规检查Agent（LangChain 高级抽象版）

    使用 ChatPromptTemplate 构建 prompt，with_structured_output 解析结果
    """

    # 输出模型
    output_model = ComplianceCheckResult

    # 各类合同的必备条款
    REQUIRED_CLAUSES = {
        "sales": ["标的物", "价款", "交付", "验收", "违约责任", "争议解决"],
        "service": ["服务内容", "服务期限", "服务费用", "验收标准", "违约责任", "保密"],
        "lease": ["租赁物", "租期", "租金", "维修责任", "违约责任", "终止条件"],
        "labor": ["工作内容", "劳动报酬", "工作时间", "社会保险", "劳动保护", "解除条件"],
        "nda": ["保密信息定义", "保密义务", "保密期限", "违约责任", "争议解决"],
        "partnership": ["出资方式", "利润分配", "亏损分担", "退出机制", "决策机制"],
        "general": ["合同标的", "价款报酬", "履行期限", "违约责任", "争议解决"],
    }

    # ==================== Prompt 模板 ====================

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同合规审查专家。请检查合同是否符合相关法律法规要求。

当前合同类型: {contract_type}
该类型合同必备条款: {required_clauses}

检查要点：
1. 必备条款是否齐全（基于合同类型）
2. 是否符合《民法典》合同编相关规定
3. 是否符合行业特殊监管要求（如劳动、数据保护等）
4. 条款内容是否合法有效
5. 免责条款是否合理
6. 争议解决条款是否有效"""),
        ("human", "请检查以下合同的合规性：\n\n{contract_text}"),
    ])

    # 增量分析模板
    incremental_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同合规审查专家。以下条款刚刚被修改，请只检查这个条款的合规性。

条款编号: {clause_id}
条款内容: {clause_text}
当前合同类型: {contract_type}
该类型合同必备条款: {required_clauses}"""),
        ("human", "请检查以下修改后条款的合规性。"),
    ])

    def __init__(
        self,
        agent_id: str = "compliance_checker",
        name: str = "合规检查Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="compliance_checker",
            description="负责检查合同是否符合相关法律法规要求",
            **kwargs
        )

        # 事件驱动：订阅 document.parsed 事件
        self._subscribed_events = [BusinessEvent.DOCUMENT_PARSED]

        logger.info(f"合规检查Agent初始化完成: {name}")

    def _get_cache_key(self) -> str:
        """获取当前会话的缓存键"""
        from .multi_turn_handler import _current_session_id
        session_id = _current_session_id.get()
        return f"{session_id}:last_result"

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理合规检查任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）
        """
        self.set_running(True)
        self.update_activity()

        try:
            # 优先从共享内存读取
            contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
            contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT) or "general"

            # 兼容旧模式
            if not contract_text:
                contract_text = task.get("contract_text", "")
            if contract_type == "general":
                contract_type = task.get("contract_type", "general")

            # 增量修改分支
            intent_type = self.read_shared("intent_type", MemoryLayer.CONTEXT)
            if intent_type == "modify_contract":
                updated_clause = self.read_shared("updated_clause", MemoryLayer.ANALYSIS)
                if updated_clause:
                    cached = self._private_memory.get_cache(self._get_cache_key()) if self._private_memory else None
                    if cached:
                        return await self._incremental_analyze(updated_clause, cached, task)

            if not contract_text:
                return {"error": "合同文本为空"}

            logger.info(f"开始合规检查，合同类型: {contract_type}，文本长度: {len(contract_text)}")

            result = await self._check_with_llm(contract_text, contract_type)

            if "error" in result:
                return result

            logger.info(f"合规检查完成，合规状态: {result.get('compliance_status', 'unknown')}")

            # 缓存结果
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), result)

            # 写入共享内存 + 发布事件
            self.write_shared("compliance_checker", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.COMPLIANCE_CHECKED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.COMPLIANCE_CHECKED}")

            return result
        except Exception as e:
            logger.error(f"合规检查Agent异常: {e}", exc_info=True)
            error_result = {"error": str(e), "compliance_status": "unknown", "checked_regulations": [], "missing_clauses": [], "compliance_violations": [], "score": 0, "summary": {}}
            self.write_shared("compliance_checker", error_result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.COMPLIANCE_CHECKED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)
            self.decrement_pending_count()

    async def _check_with_llm(self, text: str, contract_type: str) -> Dict[str, Any]:
        """
        使用 LangChain structured output 进行合规检查
        """
        required = self.REQUIRED_CLAUSES.get(contract_type, self.REQUIRED_CLAUSES["general"])

        try:
            result = await self.chat_structured(
                contract_text=text[:8000],
                contract_type=contract_type,
                required_clauses=", ".join(required),
            )
            return self._schema_to_dict(result, contract_type)
        except Exception as e:
            logger.error(f"LLM合规检查失败: {e}")
            return {
                "compliance_status": "unknown",
                "checked_regulations": [],
                "missing_clauses": [],
                "compliance_violations": [],
                "score": 0,
                "summary": {"total_checked": 0, "error": str(e)},
            }

    def _schema_to_dict(self, result: ComplianceCheckResult, contract_type: str) -> Dict[str, Any]:
        """将 Pydantic 模型转换为兼容旧格式的字典"""
        return {
            "compliance_status": result.compliance_status,
            "checked_regulations": [r.model_dump() for r in result.checked_regulations],
            "missing_clauses": result.missing_clauses,
            "compliance_violations": [v.model_dump() for v in result.compliance_violations],
            "score": result.score,
            "summary": result.summary.model_dump(),
        }

    # ==================== 增量分析 ====================

    async def _incremental_analyze(self, updated_clause: Dict[str, Any], previous_result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """单条款增量合规检查"""
        clause_text = updated_clause.get("content", "")
        clause_id = updated_clause.get("id", "")
        action = updated_clause.get("action", "replace")
        contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT) or "general"

        logger.info(f"增量合规检查: clause={clause_id}, action={action}")

        if action == "deleted":
            merged = self._merge_incremental_result(previous_result, {"compliance_violations": []}, clause_id)
            self.write_shared("compliance_checker", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            return merged

        required = self.REQUIRED_CLAUSES.get(contract_type, self.REQUIRED_CLAUSES["general"])

        try:
            # LangChain 高级抽象：structured output
            result = await self.chat_structured(
                prompt_template=self.incremental_template,
                clause_id=clause_id,
                clause_text=clause_text[:3000],
                contract_type=contract_type,
                required_clauses=", ".join(required),
            )

            new_clause_result = {
                "compliance_violations": [v.model_dump() for v in result.compliance_violations],
                "compliance_status": result.compliance_status,
                "score": result.score,
                "summary": result.summary.model_dump(),
            }

            merged = self._merge_incremental_result(previous_result, new_clause_result, clause_id)
            self.write_shared("compliance_checker", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            self.publish_event(BusinessEvent.COMPLIANCE_CHECKED, {"session_id": task.get("session_id")})
            return merged
        except Exception as e:
            logger.error(f"增量合规检查失败: {e}")

        return previous_result

    def _merge_incremental_result(self, old_result: Dict[str, Any], new_clause_result: Dict[str, Any], clause_id: str) -> Dict[str, Any]:
        """合并增量合规检查结果"""
        merged = old_result.copy()

        # 替换受影响条款的违规项
        old_violations = merged.get("compliance_violations", [])
        filtered_violations = [v for v in old_violations if clause_id not in str(v.get("related_clause", ""))]
        new_violations = new_clause_result.get("compliance_violations", [])
        for v in new_violations:
            v["related_clause"] = clause_id
        filtered_violations.extend(new_violations)

        merged["compliance_violations"] = filtered_violations

        # 更新合规状态
        if new_clause_result.get("compliance_status"):
            merged["compliance_status"] = new_clause_result["compliance_status"]
        if new_clause_result.get("score"):
            merged["score"] = new_clause_result["score"]

        merged["incremental_update"] = True
        merged["updated_clause_id"] = clause_id

        return merged
