"""
条款分析Agent模块 - LLM驱动，分析合同条款
"""
from typing import Any, Dict, List, Optional
import re
import json
import logging

from src.utils.llm_response import parse_json_from_llm

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


class ClauseAnalysisAgent(BaseAgent):
    """
    条款分析Agent（LLM驱动版）

    所有分析都使用LLM，正则作为回退
    """

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
        """获取当前会话的缓存键（使用会话级 contextvar，跨请求稳定）"""
        from .multi_turn_handler import _current_session_id
        session_id = _current_session_id.get()
        return f"{session_id}:last_result"

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理条款分析任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）

        Args:
            task: 任务数据（兼容旧模式）

        Returns:
            分析结果
        """
        self.set_running(True)
        self.update_activity()

        try:
            # 优先从共享内存读取（事件驱动模式）
            contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
            review_focus = self.read_shared("review_focus", MemoryLayer.CONTEXT) or []

            # 兼容旧模式：从 task 参数读取
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

            # 单次LLM调用完成所有分析
            result = await self._analyze_with_llm(contract_text, review_focus)

            if "error" in result:
                return result

            logger.info(f"条款分析完成，发现问题: {result.get('issues_found', 0)}个")

            # 缓存结果（供增量分析使用，按会话隔离）
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), result)

            # 阶段1：写入共享内存 + 发布事件
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
            # 聚合屏障：递减计数器（归零时自动触发 ReportGenerator）
            self.decrement_pending_count()

    async def _analyze_with_llm(self, text: str, review_focus: List[str]) -> Dict[str, Any]:
        """
        使用LLM分析条款

        Args:
            text: 合同文本
            review_focus: 审查重点

        Returns:
            分析结果
        """
        focus_instruction = ""
        if review_focus:
            focus_instruction = f"\n特别关注以下领域：{', '.join(review_focus)}"

        system_prompt = f"""你是一个专业的合同条款分析专家。请对合同进行全面分析，一次调用完成所有分析。

输出格式要求（必须是严格有效的JSON）：
{{
  "contract_type": "合同类型(sales/service/lease/labor/nda/partnership/general)",
  "completeness": {{
    "required_clauses": ["该类型合同必备条款列表"],
    "found_clauses": ["已找到的必备条款"],
    "missing_clauses": ["缺失的必备条款"],
    "completeness_score": 0.8
  }},
  "ambiguous_clauses": [
    {{
      "issue_type": "问题类型(表述模糊/范围过大/条件不明确/缺乏标准)",
      "content": "有问题的原文",
      "suggestion": "修改建议"
    }}
  ],
  "key_clauses": {{
    "条款标题1": "条款内容摘要",
    "条款标题2": "条款内容摘要"
  }},
  "rights_obligations": {{
    "rights_count": 10,
    "obligations_count": 15,
    "balance_ratio": 0.67,
    "balance_assessment": "义务偏重/权利偏重/平衡",
    "details": "具体分析"
  }},
  "issues": [
    {{
      "type": "问题类型",
      "severity": "high/medium/low",
      "message": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "summary": {{
    "total_clauses": 10,
    "total_issues": 3,
    "overall_assessment": "整体评估",
    "key_recommendations": ["关键建议1", "关键建议2"]
  }}
}}{focus_instruction}

规则：
1. 完整性分析要基于合同类型判断必备条款
2. 模糊表述要识别并给出具体修改建议
3. 权利义务分析要统计并给出平衡性判断
4. 所有问题都要给出修改建议
5. 只输出JSON，不要其他内容"""

        user_message = f"请分析以下合同条款：\n\n{text[:8000]}"

        try:
            content = await self.chat(user_message, system_prompt)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                return self._format_result(result)
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

        return {
            "sections": {},
            "analysis": {
                "completeness": {"completeness_score": 0},
                "ambiguous_clauses": [],
                "rights_obligations": {"balance_assessment": "未知"},
                "summary": {"total_issues": 0},
            },
            "missing_clauses": [],
            "issues_found": 0,
            "issues": [],
        }

    def _parse_json(self, content: str) -> Any:
        """容错JSON解析"""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        if HAS_JSON_REPAIR:
            try:
                return json_repair.loads(content)
            except Exception:
                pass

        try:
            fixed = re.sub(r',\s*([}\]])', r'\1', content)
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None

    def _format_result(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """格式化LLM结果"""
        return {
            "sections": llm_result.get("key_clauses", {}),
            "analysis": {
                "completeness": llm_result.get("completeness", {}),
                "ambiguous_clauses": llm_result.get("ambiguous_clauses", []),
                "rights_obligations": llm_result.get("rights_obligations", {}),
                "summary": llm_result.get("summary", {}),
            },
            "missing_clauses": llm_result.get("completeness", {}).get("missing_clauses", []),
            "issues_found": len(llm_result.get("issues", [])),
            "issues": llm_result.get("issues", []),
        }

    # ==================== 增量分析 ====================

    async def _incremental_analyze(self, updated_clause: Dict[str, Any], previous_result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """
        单条款增量条款分析

        Args:
            updated_clause: 更新后的条款
            previous_result: 上次的完整分析结果
            task: 任务数据

        Returns:
            合并后的条款分析结果
        """
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

        system_prompt = f"""你是一个专业的合同条款分析专家。以下条款刚刚被修改，请只分析这个条款。

条款编号: {clause_id}
条款内容: {clause_text}

输出格式要求（必须是严格有效的JSON）：
{{
  "issues": [
    {{
      "type": "问题类型",
      "severity": "high/medium/low",
      "message": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "ambiguous_clauses": [
    {{
      "issue_type": "问题类型",
      "content": "有问题的原文",
      "suggestion": "修改建议"
    }}
  ],
  "completeness": {{
    "completeness_score": 0.8
  }},
  "summary": {{
    "total_issues": 1,
    "overall_assessment": "整体评估"
  }}
}}

只输出JSON，不要其他内容"""

        user_message = f"请分析以下修改后条款：\n\n{clause_text[:3000]}"

        try:
            content = await self.chat(user_message, system_prompt)
            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                merged = self._merge_incremental_result(previous_result, result, clause_id)
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
