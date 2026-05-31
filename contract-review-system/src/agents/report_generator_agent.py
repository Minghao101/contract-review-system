"""
报告生成Agent模块 - LLM驱动，生成审查报告
"""
from typing import Any, Dict
from datetime import datetime
import re
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.llm_response import extract_llm_content, parse_json_from_llm

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


class ReportGeneratorAgent(BaseAgent):
    """
    报告生成Agent（LLM驱动版）

    使用LLM生成专业的审查报告
    """

    def __init__(
        self,
        agent_id: str = "report_generator",
        name: str = "报告生成Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="report_generator",
            description="负责生成合同审查报告",
            **kwargs
        )
        logger.info(f"报告生成Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理报告生成任务

        Args:
            task: 任务数据
                - previous_results: 前面阶段的结果

        Returns:
            报告生成结果
        """
        previous_results = task.get("previous_results", {})

        logger.info("开始生成审查报告")

        # LLM生成报告
        result = await self._generate_with_llm(previous_results)

        if "error" in result:
            return result

        logger.info("审查报告生成完成")
        return result

    async def _generate_with_llm(self, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM生成报告

        Args:
            previous_results: 前面阶段的结果

        Returns:
            报告结果
        """
        # 提取各阶段结果
        document_info = previous_results.get("parse_document", {}).get("result", {})
        clause_analysis = previous_results.get("analyze_clauses", {}).get("result", {})
        risk_assessment = previous_results.get("assess_risks", {}).get("result", {})

        # 准备上下文
        context = {
            "document_info": document_info,
            "clause_analysis": clause_analysis,
            "risk_assessment": risk_assessment,
        }

        system_prompt = """你是一个专业的合同审查报告撰写专家。请根据以下分析结果生成一份完整的合同审查报告。

输出格式要求（必须是严格有效的JSON）：
{
  "report": {
    "title": "合同审查报告",
    "executive_summary": "执行摘要（200字以内）",
    "document_overview": {
      "contract_type": "合同类型",
      "parties": ["甲方", "乙方"],
      "key_terms": "核心条款概述"
    },
    "completeness_analysis": {
      "score": 0.8,
      "found": ["已找到的条款"],
      "missing": ["缺失的条款"],
      "assessment": "完整性评估"
    },
    "risk_assessment": {
      "overall_level": "风险等级",
      "high_risks": ["高风险项"],
      "medium_risks": ["中风险项"],
      "low_risks": ["低风险项"]
    },
    "recommendations": [
      {
        "priority": "high/medium/low",
        "category": "类别",
        "content": "具体建议"
      }
    ],
    "conclusion": {
      "verdict": "建议签署/建议修改后签署/不建议签署",
      "reason": "结论原因",
      "next_steps": ["后续步骤"]
    }
  },
  "summary": {
    "risk_level": "风险等级",
    "completeness_score": 0.8,
    "total_issues": 5,
    "verdict": "最终结论"
  },
  "visualization": {
    "risk_distribution": {"high": 2, "medium": 3, "low": 1},
    "completeness_bar": 80
  }
}

规则：
1. 报告要专业、清晰、易于理解
2. 执行摘要要简洁明了
3. 风险要按严重程度分类
4. 建议要具体可执行
5. 结论要明确
6. 只输出JSON，不要其他内容"""

        human_prompt = f"""分析结果上下文：
{json.dumps(context, ensure_ascii=False, default=str)[:6000]}

请根据以上分析结果生成完整的审查报告，只输出JSON。"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = extract_llm_content(response.content)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                result["generated_at"] = datetime.now().isoformat()
                return result
        except Exception as e:
            logger.error(f"LLM报告生成失败: {e}")

        # 回退到基础报告
        return self._generate_basic_report(context)

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

    def _generate_basic_report(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成基础报告（回退）"""
        risk_assessment = context.get("risk_assessment", {})
        risk_level = risk_assessment.get("risk_level", "unknown")

        verdict_map = {
            "low": "建议签署",
            "medium": "建议修改后签署",
            "high": "建议大幅修改",
            "critical": "不建议签署",
        }

        return {
            "report": {
                "title": "合同审查报告",
                "executive_summary": "本报告基于自动化分析生成。",
                "conclusion": {
                    "verdict": verdict_map.get(risk_level, "需要人工审查"),
                    "reason": f"整体风险等级: {risk_level}",
                }
            },
            "summary": {
                "risk_level": risk_level,
                "verdict": verdict_map.get(risk_level, "需要人工审查"),
            },
            "generated_at": datetime.now().isoformat(),
        }
