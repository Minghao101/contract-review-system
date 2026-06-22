"""
风险识别Skill - LLM驱动，识别合同中的潜在风险
"""
from typing import Any, Dict, List
import logging

from ..base_skill import BaseSkill
from src.utils.llm_factory import get_llm
from src.utils.llm_response import parse_json_from_llm

logger = logging.getLogger(__name__)


class RiskIdentifierSkill(BaseSkill):
    """
    风险识别Skill（LLM驱动版）

    功能：
    - 使用LLM识别合同风险
    - 支持多类别风险检测
    - 提供风险位置定位
    """

    def __init__(self):
        super().__init__(
            skill_id="risk_identifier",
            name="风险识别",
            description="使用LLM识别合同中的潜在风险点",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行风险识别

        Args:
            **kwargs:
                - text: 合同文本（必填）
                - categories: 指定风险类别列表（可选）

        Returns:
            风险识别结果
        """
        text = kwargs.get("text", "")
        categories = kwargs.get("categories", [])

        if not text:
            return {"error": "请提供合同文本"}

        try:
            risks = await self._identify_with_llm(text, categories)

            severity_count = {"high": 0, "medium": 0, "low": 0}
            category_count = {}
            for risk in risks:
                sev = risk.get("severity", "low")
                severity_count[sev] = severity_count.get(sev, 0) + 1
                cat = risk.get("category", "other")
                category_count[cat] = category_count.get(cat, 0) + 1

            return {
                "total_risks": len(risks),
                "risks": risks,
                "severity_distribution": severity_count,
                "category_distribution": category_count,
            }
        except Exception as e:
            logger.error(f"风险识别失败: {e}")
            return {"error": str(e)}

    async def _identify_with_llm(self, text: str, categories: List[str]) -> List[Dict[str, Any]]:
        """使用LLM识别风险"""
        llm = get_llm()

        category_hint = ""
        if categories:
            category_hint = f"\n请重点关注以下风险类别: {', '.join(categories)}"

        system_prompt = f"""你是一个合同风险识别专家。请识别合同中的所有潜在风险。
{category_hint}

输出格式要求（必须是严格有效的JSON数组）：
[
  {{
    "name": "风险名称",
    "category": "liability/payment/ip/confidentiality/termination/dispute/other",
    "severity": "high/medium/low",
    "description": "风险详细描述",
    "suggestion": "修改建议"
  }}
]

识别要点：
1. 无限责任、连带责任风险
2. 预付款比例过高、违约金过高风险
3. 付款条件模糊风险
4. 知识产权归属不清、范围过宽风险
5. 保密期限过长、范围过宽风险
6. 单方解除权不对等、自动续约风险
7. 争议解决机制缺失或冲突
8. 缺少不可抗力条款
9. 履约期限过紧
10. 只输出JSON数组，不要其他内容"""

        user_message = f"请识别以下合同的风险：\n\n{text[:8000]}"

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)

            result = parse_json_from_llm(content)
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"LLM风险识别失败: {e}")
            return []
