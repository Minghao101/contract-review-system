"""
条款分析Agent模块 - 使用 LangChain 高级抽象（ChatPromptTemplate + structured output）
"""
from typing import Any, Dict, List, Optional
import logging

from langchain_core.prompts import ChatPromptTemplate

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .schemas import ClauseAnalysisResult, AmbiguousClause, AnalysisIssue
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class ClauseAnalysisAgent(BaseAgent):
    """
    条款分析Agent（LangChain 高级抽象版）

    使用 ChatPromptTemplate 构建 prompt，with_structured_output 解析结果
    """

    # 输出模型
    output_model = ClauseAnalysisResult

    # ==================== Prompt 模板 ====================

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同条款分析专家。请对合同进行全面分析。

合同类型: {contract_type}
特别关注领域: {review_focus}

分析要点：
1. 完整性分析：基于合同类型判断必备条款是否齐全
2. 模糊表述识别：找出表述不清、范围过大的条款并给出修改建议
3. 权利义务分析：统计权利和义务数量，判断平衡性
4. 问题识别：找出所有问题并按严重程度分类
5. 关键条款摘要：提取每个关键条款的核心内容"""),
        ("human", "请分析以下合同条款：\n\n{contract_text}"),
    ])

    # 增量分析模板
    incremental_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同条款分析专家。以下条款刚刚被修改，请只分析这个条款。

条款编号: {clause_id}
条款内容: {clause_text}

分析要点：
1. 识别该条款存在的问题
2. 评估表述是否清晰
3. 给出修改建议"""),
        ("human", "请分析以下修改后条款。"),
    ])

    def __init__(
        self,
        agent_id: str = "clause_analyst",
        name: str = "条款分析Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="clause_analyst",
            description="负责分析合同条款的完整性和合理性",
            **kwargs
        )

        # 事件驱动：订阅 document.parsed 事件
        self._subscribed_events = [BusinessEvent.DOCUMENT_PARSED]

        logger.info(f"条款分析Agent初始化完成: {name}")

    def _get_cache_key(self) -> str:
        """获取当前会话的缓存键"""
        from .multi_turn_handler import _current_session_id
        session_id = _current_session_id.get()
        return f"{session_id}:last_result"

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理条款分析任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）
        """
        self.set_running(True)
        self.update_activity()

        try:
            # 优先从共享内存读取
            contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
            review_focus = self.read_shared("review_focus", MemoryLayer.CONTEXT) or []

            # 兼容旧模式
            if not contract_text:
                contract_text = task.get("contract_text", "")
            if not review_focus:
                review_focus = task.get("review_focus", [])

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

            logger.info(f"开始分析合同条款，文本长度: {len(contract_text)}")

            # LangChain 高级抽象：structured output
            result = await self._analyze_with_llm(contract_text, review_focus)

            if "error" in result:
                return result

            logger.info(f"条款分析完成，发现问题: {result.get('issues_found', 0)}个")

            # 缓存结果
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), result)

            # 写入共享内存 + 发布事件
            self.write_shared("clause_analyst", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.CLAUSE_ANALYZED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.CLAUSE_ANALYZED}")

            return result
        except Exception as e:
            logger.error(f"条款分析Agent异常: {e}", exc_info=True)
            error_result = {"error": str(e), "sections": {}, "analysis": {}, "missing_clauses": [], "issues_found": 0, "issues": []}
            self.write_shared("clause_analyst", error_result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.CLAUSE_ANALYZED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)
            self.decrement_pending_count()

    async def _analyze_with_llm(self, text: str, review_focus: List[str]) -> Dict[str, Any]:
        """
        使用 LangChain structured output 分析条款

        Args:
            text: 合同文本
            review_focus: 审查重点

        Returns:
            分析结果字典
        """
        focus_str = ", ".join(review_focus) if review_focus else "无特别关注领域"

        # 获取合同类型（从共享内存）
        contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT) or "general"

        try:
            result = await self.chat_structured(
                contract_text=text[:8000],
                contract_type=contract_type,
                review_focus=focus_str,
            )
            return self._schema_to_dict(result)
        except Exception as e:
            logger.error(f"LLM条款分析失败: {e}")
            return {
                "sections": {},
                "analysis": {
                    "completeness": {"completeness_score": 0},
                    "ambiguous_clauses": [],
                    "rights_obligations": {"balance_assessment": "未知"},
                    "summary": {"total_issues": 0, "error": str(e)},
                },
                "missing_clauses": [],
                "issues_found": 0,
                "issues": [],
            }

    def _schema_to_dict(self, result: ClauseAnalysisResult) -> Dict[str, Any]:
        """将 Pydantic 模型转换为兼容旧格式的字典"""
        return {
            "sections": result.key_clauses,
            "analysis": {
                "completeness": result.completeness.model_dump(),
                "ambiguous_clauses": [a.model_dump() for a in result.ambiguous_clauses],
                "rights_obligations": result.rights_obligations.model_dump(),
                "summary": result.summary.model_dump(),
            },
            "missing_clauses": result.completeness.missing_clauses,
            "issues_found": len(result.issues),
            "issues": [i.model_dump() for i in result.issues],
        }

    # ==================== 增量分析 ====================

    async def _incremental_analyze(self, updated_clause: Dict[str, Any], previous_result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """单条款增量条款分析"""
        clause_text = updated_clause.get("content", "")
        clause_id = updated_clause.get("id", "")
        action = updated_clause.get("action", "replace")

        logger.info(f"增量条款分析: clause={clause_id}, action={action}")

        if action == "deleted":
            merged = self._merge_incremental_result(previous_result, {"issues": []}, clause_id)
            self.write_shared("clause_analyst", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            return merged

        try:
            # LangChain 高级抽象：structured output
            result = await self.chat_structured(
                prompt_template=self.incremental_template,
                clause_id=clause_id,
                clause_text=clause_text[:3000],
            )

            # 转换为字典格式并合并
            new_clause_result = {
                "issues": [i.model_dump() for i in result.issues],
                "ambiguous_clauses": [a.model_dump() for a in result.ambiguous_clauses],
                "completeness": {"completeness_score": result.completeness.completeness_score if hasattr(result, 'completeness') else 0},
                "summary": result.summary.model_dump() if hasattr(result, 'summary') else {},
            }

            merged = self._merge_incremental_result(previous_result, new_clause_result, clause_id)
            self.write_shared("clause_analyst", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            self.publish_event(BusinessEvent.CLAUSE_ANALYZED, {"session_id": task.get("session_id")})
            return merged
        except Exception as e:
            logger.error(f"增量条款分析失败: {e}")

        return previous_result

    def _merge_incremental_result(self, old_result: Dict[str, Any], new_clause_result: Dict[str, Any], clause_id: str) -> Dict[str, Any]:
        """合并增量条款分析结果"""
        merged = old_result.copy()

        # 替换受影响条款的问题
        old_issues = merged.get("issues", [])
        filtered_issues = [i for i in old_issues if clause_id not in str(i.get("related_clause", ""))]
        new_issues = new_clause_result.get("issues", [])
        for issue in new_issues:
            issue["related_clause"] = clause_id
        filtered_issues.extend(new_issues)

        merged["issues"] = filtered_issues
        merged["issues_found"] = len(filtered_issues)

        # 更新 ambiguous_clauses
        old_ambiguous = merged.get("analysis", {}).get("ambiguous_clauses", [])
        filtered_ambiguous = [a for a in old_ambiguous if clause_id not in str(a.get("related_clause", ""))]
        new_ambiguous = new_clause_result.get("ambiguous_clauses", [])
        for a in new_ambiguous:
            a["related_clause"] = clause_id
        filtered_ambiguous.extend(new_ambiguous)

        if "analysis" not in merged:
            merged["analysis"] = {}
        merged["analysis"]["ambiguous_clauses"] = filtered_ambiguous

        merged["incremental_update"] = True
        merged["updated_clause_id"] = clause_id

        return merged
