"""
风险评估Agent模块 - LLM驱动，评估合同风险
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


class RiskAssessmentAgent(BaseAgent):
    """
    风险评估Agent（LLM驱动版）

    所有风险分析都使用LLM
    """

    def __init__(
        self,
        agent_id: str = "risk_assessor",
        name: str = "风险评估Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="risk_assessor",
            description="负责评估合同风险并提供改进建议",
            **kwargs
        )
        logger.info(f"风险评估Agent初始化完成: {name}")

    def _get_cache_key(self) -> str:
        """获取当前会话的缓存键（使用会话级 contextvar，跨请求稳定）"""
        from .multi_turn_handler import _current_session_id
        session_id = _current_session_id.get()
        return f"{session_id}:last_result"

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理风险评估任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）

        Args:
            task: 任务数据（兼容旧模式）

        Returns:
            风险评估结果
        """
        self.set_running(True)
        self.update_activity()

        try:
            # 优先从共享内存读取（事件驱动模式）
            contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
            contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT) or "general"

            # 兼容旧模式：从 task 参数读取
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

            logger.info(f"开始风险评估，文本长度: {len(contract_text)}")

            # LLM风险评估
            result = await self._assess_with_llm(contract_text, contract_type)

            if "error" in result:
                return result

            # 风险量化
            risks = result.get("risks", [])
            result["risk_quantification"] = self.quantify_risk(risks)
            result["mitigation_plan"] = self.suggest_mitigation(risks)

            logger.info(f"风险评估完成，风险等级: {result.get('risk_level', 'unknown')}")

            # 缓存结果（供增量分析使用，按会话隔离）
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), result)

            # 阶段1：写入共享内存 + 发布事件
            self.write_shared("risk_assessor", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.RISK_ANALYZED}")

            return result
        except Exception as e:
            logger.error(f"风险评估Agent异常: {e}", exc_info=True)
            # 异常时发布事件，写入错误状态，保证下游不会静默阻塞
            error_result = {"error": str(e), "risk_level": "unknown", "risks": []}
            self.write_shared("risk_assessor", error_result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)
            # 聚合屏障：递减计数器（归零时自动触发 ReportGenerator）
            self.decrement_pending_count()

    async def _assess_with_llm(self, text: str, contract_type: str) -> Dict[str, Any]:
        """
        使用LLM评估风险

        Args:
            text: 合同文本
            contract_type: 合同类型

        Returns:
            风险评估结果
        """
        system_prompt = """你是一个资深的合同风险评估专家。请对合同进行全面的风险评估，一次调用完成。

输出格式要求（必须是严格有效的JSON）：
{
  "risk_level": "low/medium/high/critical",
  "risks": [
    {
      "name": "风险名称",
      "severity": "high/medium/low",
      "category": "liability/termination/payment/ip/confidentiality/dispute/other",
      "description": "风险详细描述",
      "impact": "可能的影响",
      "suggestion": "具体的修改建议"
    }
  ],
  "recommendations": [
    {
      "priority": "high/medium/low",
      "category": "类别",
      "suggestion": "具体建议",
      "reason": "建议原因"
    }
  ],
  "summary": {
    "total_risks": 5,
    "high_risks": 2,
    "medium_risks": 2,
    "low_risks": 1,
    "overall_assessment": "整体风险评估",
    "key_concerns": ["主要关注点1", "主要关注点2"]
  }
}

规则：
1. 识别所有潜在风险，包括但不限于：
   - 无限责任风险
   - 单方面解除权风险
   - 自动续约风险
   - 付款条件风险
   - 知识产权风险
   - 保密条款风险
   - 违约金过高风险
   - 管辖权风险
   - 不可抗力条款缺失
2. 每个风险都要给出具体的修改建议
3. 建议要按优先级排序
4. 只输出JSON，不要其他内容"""

        user_message = f"请对以下合同进行风险评估：\n\n{text[:8000]}"

        try:
            content = await self.chat(user_message, system_prompt)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.error(f"LLM风险评估失败: {e}")
            return {
                "risk_level": "unknown",
                "risks": [],
                "recommendations": [],
                "summary": {"total_risks": 0, "error": str(e)}
            }

    def quantify_risk(self, risks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        量化风险评估

        Args:
            risks: 风险列表

        Returns:
            风险量化结果
        """
        severity_weights = {"high": 3, "medium": 2, "low": 1}
        category_weights = {
            "liability": 1.5,
            "payment": 1.3,
            "ip": 1.4,
            "termination": 1.2,
            "dispute": 1.3,
            "confidentiality": 1.1,
        }

        total_weighted_score = 0
        distribution = {"high": 0, "medium": 0, "low": 0}
        category_scores = {}

        for risk in risks:
            severity = risk.get("severity", "low")
            category = risk.get("category", "other")

            sev_weight = severity_weights.get(severity, 1)
            cat_weight = category_weights.get(category, 1.0)
            risk_score = sev_weight * cat_weight

            total_weighted_score += risk_score
            distribution[severity] = distribution.get(severity, 0) + 1

            if category not in category_scores:
                category_scores[category] = 0
            category_scores[category] += risk_score

        # 归一化到 0-100 分（风险越高分数越高）
        max_possible = len(risks) * 3 * 1.5 if risks else 1
        normalized_score = min(100, int((total_weighted_score / max_possible) * 100))

        return {
            "risk_score": normalized_score,
            "total_weighted_score": round(total_weighted_score, 2),
            "risk_distribution": distribution,
            "category_scores": {k: round(v, 2) for k, v in category_scores.items()},
            "total_risks": len(risks),
        }

    def suggest_mitigation(self, risks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        为高/中风险生成缓解建议

        Args:
            risks: 风险列表

        Returns:
            缓解计划列表
        """
        mitigation_templates = {
            "liability": {
                "mitigation": "建议设置责任上限，明确赔偿范围和免责条款",
                "estimated_cost": "low",
            },
            "payment": {
                "mitigation": "建议明确付款节点、逾期利息和付款条件",
                "estimated_cost": "low",
            },
            "ip": {
                "mitigation": "建议明确知识产权归属、使用范围和侵权责任",
                "estimated_cost": "medium",
            },
            "termination": {
                "mitigation": "建议增加提前通知期，明确终止后的权利义务处理",
                "estimated_cost": "low",
            },
            "dispute": {
                "mitigation": "建议约定争议解决方式（仲裁/诉讼）和管辖法院",
                "estimated_cost": "low",
            },
            "confidentiality": {
                "mitigation": "建议限定保密范围和期限，明确违约责任",
                "estimated_cost": "low",
            },
        }

        mitigation_plan = []
        for risk in risks:
            if risk.get("severity") in ("high", "medium"):
                category = risk.get("category", "other")
                template = mitigation_templates.get(category, {
                    "mitigation": "建议与专业法律顾问确认相关条款",
                    "estimated_cost": "medium",
                })

                mitigation_plan.append({
                    "risk_name": risk.get("name", "未知风险"),
                    "severity": risk.get("severity"),
                    "mitigation": risk.get("suggestion", template["mitigation"]),
                    "priority": "high" if risk.get("severity") == "high" else "medium",
                    "estimated_cost": template["estimated_cost"],
                })

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1}
        mitigation_plan.sort(key=lambda x: priority_order.get(x["priority"], 2))

        return mitigation_plan

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

    # ==================== 增量分析 ====================

    async def _incremental_analyze(self, updated_clause: Dict[str, Any], previous_result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """
        单条款增量风险分析

        Args:
            updated_clause: 更新后的条款
            previous_result: 上次的完整分析结果
            task: 任务数据

        Returns:
            合并后的风险评估结果
        """
        clause_text = updated_clause.get("content", "")
        clause_id = updated_clause.get("id", "")
        action = updated_clause.get("action", "replace")

        logger.info(f"增量风险分析: clause={clause_id}, action={action}")

        if action == "deleted":
            # 条款被删除：从结果中移除相关风险
            merged = self._merge_incremental_result(previous_result, {"risks": [], "risk_level": previous_result.get("risk_level")}, clause_id)
            # 重新计算量化指标
            risks = merged.get("risks", [])
            merged["risk_quantification"] = self.quantify_risk(risks)
            merged["mitigation_plan"] = self.suggest_mitigation(risks)
            self.write_shared("risk_assessor", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            return merged

        system_prompt = f"""你是一个资深的合同风险评估专家。以下条款刚刚被修改，请只评估这个条款的风险。

条款编号: {clause_id}
条款内容: {clause_text}

输出格式要求（必须是严格有效的JSON）：
{{
  "risks": [
    {{
      "name": "风险名称",
      "severity": "high/medium/low",
      "category": "liability/termination/payment/ip/confidentiality/dispute/other",
      "description": "风险详细描述",
      "impact": "可能的影响",
      "suggestion": "具体的修改建议"
    }}
  ],
  "risk_level": "low/medium/high/critical",
  "summary": {{
    "total_risks": 1,
    "overall_assessment": "整体评估"
  }}
}}

只输出JSON，不要其他内容"""

        user_message = f"请评估以下修改后条款的风险：\n\n{clause_text[:3000]}"

        try:
            content = await self.chat(user_message, system_prompt)
            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                merged = self._merge_incremental_result(previous_result, result, clause_id)
                # 重新计算量化指标
                risks = merged.get("risks", [])
                merged["risk_quantification"] = self.quantify_risk(risks)
                merged["mitigation_plan"] = self.suggest_mitigation(risks)
                self.write_shared("risk_assessor", merged, MemoryLayer.ANALYSIS, validate=False)
                # 缓存结果（按会话隔离）
                if self._private_memory:
                    self._private_memory.set_cache(self._get_cache_key(), merged)
                # 发布事件
                self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
                return merged
        except Exception as e:
            logger.error(f"增量风险分析失败: {e}")

        # 降级：返回上次结果
        return previous_result

    def _merge_incremental_result(self, old_result: Dict[str, Any], new_clause_result: Dict[str, Any], clause_id: str) -> Dict[str, Any]:
        """
        合并增量分析结果

        Args:
            old_result: 上次的完整结果
            new_clause_result: 新条款的分析结果
            clause_id: 被修改的条款ID

        Returns:
            合并后的结果
        """
        merged = old_result.copy()

        # 替换受影响条款的风险
        old_risks = merged.get("risks", [])
        # 过滤掉旧条款相关风险
        filtered_risks = [r for r in old_risks if clause_id not in str(r.get("related_clause", ""))]
        # 添加新风险
        new_risks = new_clause_result.get("risks", [])
        for risk in new_risks:
            risk["related_clause"] = clause_id
        filtered_risks.extend(new_risks)

        merged["risks"] = filtered_risks

        # 更新风险等级
        if new_clause_result.get("risk_level"):
            merged["risk_level"] = new_clause_result["risk_level"]

        # 标记为增量更新
        merged["incremental_update"] = True
        merged["updated_clause_id"] = clause_id

        # 更新 summary
        if "summary" in merged:
            merged["summary"]["total_risks"] = len(filtered_risks)
            high_count = sum(1 for r in filtered_risks if r.get("severity") == "high")
            medium_count = sum(1 for r in filtered_risks if r.get("severity") == "medium")
            low_count = sum(1 for r in filtered_risks if r.get("severity") == "low")
            merged["summary"]["high_risks"] = high_count
            merged["summary"]["medium_risks"] = medium_count
            merged["summary"]["low_risks"] = low_count

        return merged
