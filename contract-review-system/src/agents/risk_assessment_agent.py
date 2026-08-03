"""
风险评估Agent模块 - 使用 LangChain 高级抽象（ChatPromptTemplate + structured output）
"""
from typing import Any, Dict, List, Optional
import logging

from langchain_core.prompts import ChatPromptTemplate

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .schemas import RiskAssessmentResult
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class RiskAssessmentAgent(BaseAgent):
    """
    风险评估Agent（LangChain 高级抽象版）

    使用 ChatPromptTemplate 构建 prompt，with_structured_output 解析结果
    """

    # 输出模型
    output_model = RiskAssessmentResult

    # ==================== Prompt 模板 ====================

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个资深的合同风险评估专家。请对合同进行全面的风险评估。

识别所有潜在风险，包括但不限于：
- 无限责任风险
- 单方面解除权风险
- 自动续约风险
- 付款条件风险
- 知识产权风险
- 保密条款风险
- 违约金过高风险
- 管辖权风险
- 不可抗力条款缺失

每个风险都要给出具体的修改建议，建议要按优先级排序。"""),
        ("human", "请对以下合同进行风险评估：\n\n{contract_text}"),
    ])

    # 增量分析模板
    incremental_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个资深的合同风险评估专家。以下条款刚刚被修改，请只评估这个条款的风险。

条款编号: {clause_id}
条款内容: {clause_text}"""),
        ("human", "请评估以下修改后条款的风险。"),
    ])

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

        # 事件驱动：订阅 document.parsed 事件
        self._subscribed_events = [BusinessEvent.DOCUMENT_PARSED]

        logger.info(f"风险评估Agent初始化完成: {name}")

    def _get_cache_key(self) -> str:
        """获取当前会话的缓存键"""
        from .multi_turn_handler import _current_session_id
        session_id = _current_session_id.get()
        return f"{session_id}:last_result"

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理风险评估任务

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

            logger.info(f"开始风险评估，文本长度: {len(contract_text)}")

            result = await self._assess_with_llm(contract_text, contract_type)

            if "error" in result:
                return result

            # 风险量化
            risks = result.get("risks", [])
            result["risk_quantification"] = self.quantify_risk(risks)
            result["mitigation_plan"] = self.suggest_mitigation(risks)

            logger.info(f"风险评估完成，风险等级: {result.get('risk_level', 'unknown')}")

            # 缓存结果
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), result)

            # 写入共享内存 + 发布事件
            self.write_shared("risk_assessor", result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.RISK_ANALYZED}")

            return result
        except Exception as e:
            logger.error(f"风险评估Agent异常: {e}", exc_info=True)
            error_result = {"error": str(e), "risk_level": "unknown", "risks": []}
            self.write_shared("risk_assessor", error_result, MemoryLayer.ANALYSIS, validate=False)
            self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)
            self.decrement_pending_count()

    async def _assess_with_llm(self, text: str, contract_type: str) -> Dict[str, Any]:
        """
        使用 LangChain structured output 评估风险
        """
        try:
            result = await self.chat_structured(
                contract_text=text[:8000],
            )
            return self._schema_to_dict(result)
        except Exception as e:
            logger.error(f"LLM风险评估失败: {e}")
            return {
                "risk_level": "unknown",
                "risks": [],
                "recommendations": [],
                "summary": {"total_risks": 0, "error": str(e)}
            }

    def _schema_to_dict(self, result: RiskAssessmentResult) -> Dict[str, Any]:
        """将 Pydantic 模型转换为兼容旧格式的字典"""
        return {
            "risk_level": result.risk_level,
            "risks": [r.model_dump() for r in result.risks],
            "recommendations": [rec.model_dump() for rec in result.recommendations],
            "summary": result.summary.model_dump(),
        }

    def quantify_risk(self, risks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """量化风险评估"""
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
        """为高/中风险生成缓解建议"""
        mitigation_templates = {
            "liability": {"mitigation": "建议设置责任上限，明确赔偿范围和免责条款", "estimated_cost": "low"},
            "payment": {"mitigation": "建议明确付款节点、逾期利息和付款条件", "estimated_cost": "low"},
            "ip": {"mitigation": "建议明确知识产权归属、使用范围和侵权责任", "estimated_cost": "medium"},
            "termination": {"mitigation": "建议增加提前通知期，明确终止后的权利义务处理", "estimated_cost": "low"},
            "dispute": {"mitigation": "建议约定争议解决方式（仲裁/诉讼）和管辖法院", "estimated_cost": "low"},
            "confidentiality": {"mitigation": "建议限定保密范围和期限，明确违约责任", "estimated_cost": "low"},
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

        priority_order = {"high": 0, "medium": 1}
        mitigation_plan.sort(key=lambda x: priority_order.get(x["priority"], 2))

        return mitigation_plan

    # ==================== 增量分析 ====================

    async def _incremental_analyze(self, updated_clause: Dict[str, Any], previous_result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """单条款增量风险分析"""
        clause_text = updated_clause.get("content", "")
        clause_id = updated_clause.get("id", "")
        action = updated_clause.get("action", "replace")

        logger.info(f"增量风险分析: clause={clause_id}, action={action}")

        if action == "deleted":
            merged = self._merge_incremental_result(previous_result, {"risks": [], "risk_level": previous_result.get("risk_level")}, clause_id)
            risks = merged.get("risks", [])
            merged["risk_quantification"] = self.quantify_risk(risks)
            merged["mitigation_plan"] = self.suggest_mitigation(risks)
            self.write_shared("risk_assessor", merged, MemoryLayer.ANALYSIS, validate=False)
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

            new_clause_result = {
                "risks": [r.model_dump() for r in result.risks],
                "risk_level": result.risk_level,
                "summary": result.summary.model_dump(),
            }

            merged = self._merge_incremental_result(previous_result, new_clause_result, clause_id)
            risks = merged.get("risks", [])
            merged["risk_quantification"] = self.quantify_risk(risks)
            merged["mitigation_plan"] = self.suggest_mitigation(risks)
            self.write_shared("risk_assessor", merged, MemoryLayer.ANALYSIS, validate=False)
            if self._private_memory:
                self._private_memory.set_cache(self._get_cache_key(), merged)
            self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": task.get("session_id")})
            return merged
        except Exception as e:
            logger.error(f"增量风险分析失败: {e}")

        return previous_result

    def _merge_incremental_result(self, old_result: Dict[str, Any], new_clause_result: Dict[str, Any], clause_id: str) -> Dict[str, Any]:
        """合并增量分析结果"""
        merged = old_result.copy()

        old_risks = merged.get("risks", [])
        filtered_risks = [r for r in old_risks if clause_id not in str(r.get("related_clause", ""))]
        new_risks = new_clause_result.get("risks", [])
        for risk in new_risks:
            risk["related_clause"] = clause_id
        filtered_risks.extend(new_risks)

        merged["risks"] = filtered_risks

        if new_clause_result.get("risk_level"):
            merged["risk_level"] = new_clause_result["risk_level"]

        merged["incremental_update"] = True
        merged["updated_clause_id"] = clause_id

        if "summary" in merged:
            merged["summary"]["total_risks"] = len(filtered_risks)
            high_count = sum(1 for r in filtered_risks if r.get("severity") == "high")
            medium_count = sum(1 for r in filtered_risks if r.get("severity") == "medium")
            low_count = sum(1 for r in filtered_risks if r.get("severity") == "low")
            merged["summary"]["high_risks"] = high_count
            merged["summary"]["medium_risks"] = medium_count
            merged["summary"]["low_risks"] = low_count

        return merged
