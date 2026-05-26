"""
风险评估Agent模块 - LLM驱动，评估合同风险
"""
from typing import Any, Dict, List, Optional
import re
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent

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

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理风险评估任务

        Args:
            task: 任务数据
                - contract_text: 合同文本
                - contract_type: 合同类型 (可选)

        Returns:
            风险评估结果
        """
        contract_text = task.get("contract_text", "")
        contract_type = task.get("contract_type", "general")

        if not contract_text:
            return {"error": "合同文本为空"}

        logger.info(f"开始风险评估，文本长度: {len(contract_text)}")

        # LLM风险评估
        result = await self._assess_with_llm(contract_text, contract_type)

        if "error" in result:
            return result

        logger.info(f"风险评估完成，风险等级: {result.get('risk_level', 'unknown')}")
        return result

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

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请对以下合同进行风险评估：\n\n{text[:8000]}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = response.content

            if isinstance(content, list):
                content = content[0].get("text", "") if content else ""

            result = self._parse_json(content.strip())

            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.error(f"LLM风险评估失败: {e}")

        # 回退到基础评估
        return self._assess_with_regex(text)

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

    def _assess_with_regex(self, text: str) -> Dict[str, Any]:
        """正则回退评估"""
        risks = []

        # 简单的风险检测
        risk_patterns = [
            (r"无限责任", "无限责任风险", "high"),
            (r"单方面?解除", "单方解除风险", "high"),
            (r"自动续约", "自动续约风险", "medium"),
            (r"永久保密", "保密期限过长", "medium"),
        ]

        for pattern, name, severity in risk_patterns:
            if re.search(pattern, text):
                risks.append({
                    "name": name,
                    "severity": severity,
                    "category": "other",
                    "description": f"检测到{name}",
                    "suggestion": "建议修改相关条款"
                })

        risk_level = "low"
        if any(r["severity"] == "high" for r in risks):
            risk_level = "high"
        elif any(r["severity"] == "medium" for r in risks):
            risk_level = "medium"

        return {
            "risk_level": risk_level,
            "risks": risks,
            "recommendations": [],
            "summary": {
                "total_risks": len(risks),
                "high_risks": len([r for r in risks if r["severity"] == "high"]),
                "medium_risks": len([r for r in risks if r["severity"] == "medium"]),
                "low_risks": len([r for r in risks if r["severity"] == "low"]),
            }
        }
