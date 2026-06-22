"""
条款解析Skill - LLM驱动，解析合同条款结构和内容
"""
from typing import Any, Dict, List, Optional
import re
import logging

from ..base_skill import BaseSkill
from src.utils.llm_factory import get_llm
from src.utils.llm_response import parse_json_from_llm

logger = logging.getLogger(__name__)


class ClauseParserSkill(BaseSkill):
    """
    条款解析Skill（LLM驱动版）

    功能：
    - 识别合同条款层级结构
    - 使用LLM分析条款类型和关键信息
    - 检测条款间的引用关系
    """

    def __init__(self):
        super().__init__(
            skill_id="clause_parser",
            name="条款解析",
            description="解析合同条款结构，使用LLM分析条款信息并识别条款类型",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行条款解析

        Args:
            **kwargs:
                - text: 合同文本（必填）

        Returns:
            条款解析结果
        """
        text = kwargs.get("text", "")

        if not text:
            return {"error": "请提供合同文本"}

        try:
            # 1. 提取条款结构（使用正则解析文档结构）
            clauses = self._extract_clauses(text)

            # 2. 使用LLM分析条款类型和关键信息
            analyzed_clauses = await self._analyze_with_llm(clauses)

            # 3. 识别条款类型分布
            type_distribution = self._get_type_distribution(analyzed_clauses)

            # 4. 检测条款引用关系
            references = self._detect_references(analyzed_clauses)

            return {
                "total_clauses": len(analyzed_clauses),
                "clauses": analyzed_clauses,
                "type_distribution": type_distribution,
                "references": references,
                "summary": {
                    "has_liability_clauses": any(
                        c.get("clause_type") == "违约" for c in analyzed_clauses
                    ),
                    "has_dispute_resolution": any(
                        c.get("clause_type") == "争议解决" for c in analyzed_clauses
                    ),
                    "has_confidentiality": any(
                        c.get("clause_type") == "保密" for c in analyzed_clauses
                    ),
                },
            }
        except Exception as e:
            logger.error(f"条款解析失败: {e}")
            return {"error": str(e)}

    def _extract_clauses(self, text: str) -> List[Dict[str, Any]]:
        """提取条款结构"""
        patterns = [
            r"(?:第[一二三四五六七八九十百千]+条)\s*[：:]*\s*(.+?)(?=第[一二三四五六七八九十百千]+条|$)",
            r"(?:\d+[\.\、])\s*(.+?)(?=\d+[\.\、]|$)",
            r"(?:[（(]\s*[一二三四五六七八九十\d]+\s*[)）])\s*(.+?)(?=[（(]\s*[一二三四五六七八九十\d]+\s*[)）]|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                clauses = []
                for i, match in enumerate(matches):
                    content = match.strip()
                    if len(content) > 5:
                        clauses.append({
                            "index": i + 1,
                            "content": content,
                        })
                if clauses:
                    return clauses

        # 回退：按段落分割
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        return [
            {"index": i + 1, "content": p}
            for i, p in enumerate(paragraphs)
            if len(p) > 10
        ]

    async def _analyze_with_llm(self, clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用LLM分析条款类型和关键信息"""
        if not clauses:
            return []

        llm = get_llm()

        # 构建条款摘要（避免超长）
        clause_texts = []
        for c in clauses[:30]:  # 限制最多30条
            content = c["content"][:500]
            clause_texts.append(f"第{c['index']}条: {content}")

        system_prompt = """你是一个合同条款分析专家。请分析每个条款的类型和关键信息。

条款类型包括：权利、义务、免责、违约、付款、交付、保密、知识产权、争议解决、终止、其他

输出格式要求（必须是严格有效的JSON数组）：
[
  {
    "index": 1,
    "clause_type": "条款类型",
    "key_info": {
      "amount": "金额（如有）",
      "date": "日期（如有）",
      "percentage": "百分比（如有）",
      "duration": "期限（如有）"
    }
  }
]

只输出JSON数组，不要其他内容"""

        user_message = f"请分析以下合同条款：\n\n" + "\n\n".join(clause_texts)

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)

            result = parse_json_from_llm(content)

            if isinstance(result, list):
                # 合并LLM结果到原始条款
                analysis_map = {item.get("index"): item for item in result if isinstance(item, dict)}
                for clause in clauses:
                    analysis = analysis_map.get(clause["index"], {})
                    clause["clause_type"] = analysis.get("clause_type", "其他")
                    clause["key_info"] = analysis.get("key_info", {})
                    clause["char_count"] = len(clause["content"])
                return clauses
        except Exception as e:
            logger.error(f"LLM条款分析失败: {e}")

        # 回退：返回原始条款
        for clause in clauses:
            clause["clause_type"] = "其他"
            clause["key_info"] = {}
            clause["char_count"] = len(clause["content"])
        return clauses

    def _get_type_distribution(self, clauses: List[Dict]) -> Dict[str, int]:
        """获取条款类型分布"""
        distribution = {}
        for clause in clauses:
            t = clause.get("clause_type", "其他")
            distribution[t] = distribution.get(t, 0) + 1
        return distribution

    def _detect_references(self, clauses: List[Dict]) -> List[Dict[str, Any]]:
        """检测条款间的引用关系"""
        references = []
        for clause in clauses:
            content = clause["content"]
            ref_matches = re.findall(
                r"(?:按照|参照|依据|根据|见)\s*第?\s*([一二三四五六七八九十\d]+)\s*条",
                content,
            )
            for ref in ref_matches:
                references.append({
                    "from_clause": clause["index"],
                    "reference_to": ref,
                    "context": content[:50] + "...",
                })
        return references
