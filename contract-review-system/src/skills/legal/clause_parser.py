"""
条款解析Skill - 解析合同条款结构和内容
"""
from typing import Any, Dict, List, Optional
import re
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class ClauseParserSkill(BaseSkill):
    """
    条款解析Skill

    功能：
    - 识别合同条款层级结构
    - 提取条款关键信息（编号、标题、内容）
    - 识别条款类型（权利条款、义务条款、免责条款等）
    - 检测条款间的引用关系
    """

    # 条款类型关键词映射
    CLAUSE_TYPE_KEYWORDS = {
        "权利": ["有权", "权利", "可以", "享有", "主张"],
        "义务": ["应当", "必须", "有义务", "负责", "承担"],
        "免责": ["免责", "不承担", "免除", "概不负责"],
        "违约": ["违约", "赔偿", "损失", "罚则", "违约金"],
        "付款": ["付款", "支付", "结算", "账期", "发票"],
        "交付": ["交付", "交货", "发货", "运输", "签收"],
        "保密": ["保密", "机密", "秘密", "不得泄露"],
        "知识产权": ["知识产权", "著作权", "专利", "商标", "版权"],
        "争议解决": ["争议", "纠纷", "仲裁", "诉讼", "管辖"],
        "终止": ["终止", "解除", "到期", "续约", "退出"],
    }

    def __init__(self):
        super().__init__(
            skill_id="clause_parser",
            name="条款解析",
            description="解析合同条款结构，提取条款信息并识别条款类型",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行条款解析

        Args:
            **kwargs:
                - text: 合同文本（必填）
                - clause_pattern: 自定义条款匹配正则（可选）

        Returns:
            条款解析结果
        """
        text = kwargs.get("text", "")
        clause_pattern = kwargs.get("clause_pattern")

        if not text:
            return {"error": "请提供合同文本"}

        try:
            # 1. 识别条款结构
            clauses = self._extract_clauses(text, clause_pattern)

            # 2. 分析每个条款
            analyzed_clauses = []
            for clause in clauses:
                analyzed = self._analyze_clause(clause)
                analyzed_clauses.append(analyzed)

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
                        c["clause_type"] == "违约" for c in analyzed_clauses
                    ),
                    "has_dispute_resolution": any(
                        c["clause_type"] == "争议解决" for c in analyzed_clauses
                    ),
                    "has_confidentiality": any(
                        c["clause_type"] == "保密" for c in analyzed_clauses
                    ),
                },
            }
        except Exception as e:
            logger.error(f"条款解析失败: {e}")
            return {"error": str(e)}

    def _extract_clauses(
        self, text: str, custom_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        提取条款结构

        Args:
            text: 合同文本
            custom_pattern: 自定义匹配正则

        Returns:
            条款列表
        """
        # 默认条款匹配模式
        patterns = [
            custom_pattern,
            r"(?:第[一二三四五六七八九十百千]+条)\s*[：:]*\s*(.+?)(?=第[一二三四五六七八九十百千]+条|$)",
            r"(?:\d+[\.\、])\s*(.+?)(?=\d+[\.\、]|$)",
            r"(?:[（(]\s*[一二三四五六七八九十\d]+\s*[)）])\s*(.+?)(?=[（(]\s*[一二三四五六七八九十\d]+\s*[)）]|$)",
        ]

        for pattern in patterns:
            if pattern is None:
                continue
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                clauses = []
                for i, match in enumerate(matches):
                    content = match.strip()
                    if len(content) > 5:  # 过滤太短的匹配
                        clauses.append({
                            "index": i + 1,
                            "content": content,
                            "raw_text": match,
                        })
                if clauses:
                    return clauses

        # 回退：按段落分割
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        return [
            {"index": i + 1, "content": p, "raw_text": p}
            for i, p in enumerate(paragraphs)
            if len(p) > 10
        ]

    def _analyze_clause(self, clause: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析单个条款

        Args:
            clause: 条款数据

        Returns:
            分析后的条款
        """
        content = clause["content"]

        # 识别条款类型
        clause_type = self._identify_clause_type(content)

        # 提取关键信息
        key_info = self._extract_key_info(content)

        return {
            "index": clause["index"],
            "content": content,
            "clause_type": clause_type,
            "key_info": key_info,
            "char_count": len(content),
        }

    def _identify_clause_type(self, content: str) -> str:
        """识别条款类型"""
        scores = {}
        for clause_type, keywords in self.CLAUSE_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                scores[clause_type] = score

        if scores:
            return max(scores, key=scores.get)
        return "其他"

    def _extract_key_info(self, content: str) -> Dict[str, Any]:
        """提取条款关键信息"""
        info = {}

        # 提取金额
        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|万|美元|USD|CNY)", content)
        if amount_match:
            info["amount"] = amount_match.group(0)

        # 提取日期
        date_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", content)
        if date_match:
            info["date"] = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

        # 提取百分比
        percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", content)
        if percent_match:
            info["percentage"] = percent_match.group(0)

        # 提取时间期限
        duration_match = re.search(r"(\d+)\s*(?:天|日|个月|月|年)", content)
        if duration_match:
            info["duration"] = duration_match.group(0)

        return info

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
            # 检测"按照第X条"、"参照本合同第X条"等引用
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
