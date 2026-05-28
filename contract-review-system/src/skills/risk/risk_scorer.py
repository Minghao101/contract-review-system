"""
风险量化Skill - 对识别出的风险进行量化评分
"""
from typing import Any, Dict, List
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class RiskScorerSkill(BaseSkill):
    """
    风险量化Skill

    功能：
    - 根据风险严重程度和类别计算风险分数
    - 生成风险矩阵
    - 提供整体风险评估
    """

    # 严重程度权重
    SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}

    # 类别权重（对业务影响越大权重越高）
    CATEGORY_WEIGHTS = {
        "liability": 1.5,
        "payment": 1.3,
        "ip": 1.4,
        "termination": 1.2,
        "dispute": 1.3,
        "confidentiality": 1.1,
        "other": 1.0,
    }

    # 风险等级阈值
    RISK_THRESHOLDS = {
        "critical": 80,
        "high": 60,
        "medium": 40,
        "low": 0,
    }

    def __init__(self):
        super().__init__(
            skill_id="risk_scorer",
            name="风险量化",
            description="对识别出的风险进行量化评分，生成风险矩阵",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行风险量化

        Args:
            **kwargs:
                - risks: 风险列表（必填，来自RiskIdentifierSkill的输出）

        Returns:
            风险量化结果
        """
        risks = kwargs.get("risks", [])

        if not risks:
            return {"error": "请提供风险列表"}

        try:
            # 1. 计算每个风险的分数
            scored_risks = self._score_risks(risks)

            # 2. 计算整体风险分数
            overall_score = self._calculate_overall_score(scored_risks)

            # 3. 确定风险等级
            risk_level = self._determine_risk_level(overall_score)

            # 4. 生成风险矩阵
            risk_matrix = self._build_risk_matrix(scored_risks)

            # 5. 分类统计
            category_stats = self._calculate_category_stats(scored_risks)

            return {
                "overall_score": overall_score,
                "risk_level": risk_level,
                "total_risks": len(scored_risks),
                "scored_risks": scored_risks,
                "risk_matrix": risk_matrix,
                "category_stats": category_stats,
                "summary": {
                    "critical_count": len([r for r in scored_risks if r["risk_level"] == "critical"]),
                    "high_count": len([r for r in scored_risks if r["risk_level"] == "high"]),
                    "medium_count": len([r for r in scored_risks if r["risk_level"] == "medium"]),
                    "low_count": len([r for r in scored_risks if r["risk_level"] == "low"]),
                },
            }
        except Exception as e:
            logger.error(f"风险量化失败: {e}")
            return {"error": str(e)}

    def _score_risks(self, risks: List[Dict]) -> List[Dict[str, Any]]:
        """为每个风险计算分数"""
        scored = []
        for risk in risks:
            severity = risk.get("severity", "low")
            category = risk.get("category", "other")

            sev_weight = self.SEVERITY_WEIGHTS.get(severity, 1)
            cat_weight = self.CATEGORY_WEIGHTS.get(category, 1.0)

            # 风险分数 = 严重程度权重 × 类别权重 × 10（归一化到0-100范围的基础）
            raw_score = sev_weight * cat_weight * 10
            score = min(100, int(raw_score))

            risk_level = self._determine_risk_level(score)

            scored.append({
                **risk,
                "score": score,
                "risk_level": risk_level,
                "severity_weight": sev_weight,
                "category_weight": cat_weight,
            })

        # 按分数降序排列
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _calculate_overall_score(self, scored_risks: List[Dict]) -> int:
        """计算整体风险分数"""
        if not scored_risks:
            return 0

        # 加权平均：高分风险影响更大
        total_weight = 0
        weighted_sum = 0
        for risk in scored_risks:
            weight = risk["score"]
            weighted_sum += risk["score"] * weight
            total_weight += weight

        if total_weight == 0:
            return 0

        return min(100, int(weighted_sum / total_weight))

    def _determine_risk_level(self, score: int) -> str:
        """根据分数确定风险等级"""
        for level, threshold in self.RISK_THRESHOLDS.items():
            if score >= threshold:
                return level
        return "low"

    def _build_risk_matrix(self, scored_risks: List[Dict]) -> Dict[str, List]:
        """生成风险矩阵"""
        matrix = {"critical": [], "high": [], "medium": [], "low": []}
        for risk in scored_risks:
            level = risk.get("risk_level", "low")
            if level in matrix:
                matrix[level].append({
                    "name": risk.get("name", ""),
                    "score": risk.get("score", 0),
                    "category": risk.get("category", ""),
                })
        return matrix

    def _calculate_category_stats(self, scored_risks: List[Dict]) -> Dict[str, Any]:
        """按类别统计风险"""
        stats = {}
        for risk in scored_risks:
            cat = risk.get("category", "other")
            if cat not in stats:
                stats[cat] = {"count": 0, "total_score": 0, "avg_score": 0, "max_severity": "low"}
            stats[cat]["count"] += 1
            stats[cat]["total_score"] += risk.get("score", 0)
            # 更新最高严重程度
            sev_order = {"high": 3, "medium": 2, "low": 1}
            if sev_order.get(risk.get("severity", "low"), 0) > sev_order.get(stats[cat]["max_severity"], 0):
                stats[cat]["max_severity"] = risk.get("severity", "low")

        # 计算平均分
        for cat in stats:
            if stats[cat]["count"] > 0:
                stats[cat]["avg_score"] = round(stats[cat]["total_score"] / stats[cat]["count"], 1)

        return stats
