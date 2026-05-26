"""
条款分析Agent模块 - LLM驱动，分析合同条款
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
        logger.info(f"条款分析Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理条款分析任务

        Args:
            task: 任务数据
                - contract_text: 合同文本
                - review_focus: 审查重点 (可选)

        Returns:
            分析结果
        """
        contract_text = task.get("contract_text", "")
        review_focus = task.get("review_focus", [])

        if not contract_text:
            return {"error": "合同文本为空"}

        logger.info(f"开始分析合同条款，文本长度: {len(contract_text)}")

        # 单次LLM调用完成所有分析
        result = await self._analyze_with_llm(contract_text, review_focus)

        if "error" in result:
            return result

        logger.info(f"条款分析完成，发现问题: {result.get('issues_found', 0)}个")
        return result

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

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请分析以下合同条款：\n\n{text[:8000]}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = response.content

            if isinstance(content, list):
                content = content[0].get("text", "") if content else ""

            result = self._parse_json(content.strip())

            if isinstance(result, dict):
                return self._format_result(result)
        except Exception as e:
            logger.error(f"LLM条款分析失败: {e}")

        # 回退到正则分析
        return self._analyze_with_regex(text)

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

    def _analyze_with_regex(self, text: str) -> Dict[str, Any]:
        """正则回退分析"""
        # 简单的正则分析
        ambiguous = []
        ambiguous_patterns = [
            (r"合理[的地]?时间", "时间表述模糊"),
            (r"适当[的地]?方式", "方式表述模糊"),
            (r"必要[的地]?措施", "措施表述模糊"),
        ]

        for pattern, issue_type in ambiguous_patterns:
            for match in re.finditer(pattern, text):
                ambiguous.append({
                    "issue_type": issue_type,
                    "content": match.group(0),
                    "suggestion": "建议明确具体时间/方式/措施"
                })

        return {
            "sections": {},
            "analysis": {
                "completeness": {"completeness_score": 0},
                "ambiguous_clauses": ambiguous,
                "rights_obligations": {"balance_assessment": "未知"},
                "summary": {"total_issues": len(ambiguous)},
            },
            "missing_clauses": [],
            "issues_found": len(ambiguous),
            "issues": ambiguous,
        }
