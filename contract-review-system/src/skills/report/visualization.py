"""
可视化Skill - 生成报告的可视化数据和图表配置
"""
from typing import Any, Dict, List, Optional
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class VisualizationSkill(BaseSkill):
    """
    可视化Skill

    功能：
    - 生成风险分布图表数据
    - 生成合规评分雷达图数据
    - 生成条款完整性进度条数据
    - 生成综合评分仪表盘数据
    """

    def __init__(self):
        super().__init__(
            skill_id="visualization",
            name="报告可视化",
            description="生成合同审查报告的可视化图表数据",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        report_data = kwargs.get("report_data", {})
        chart_types = kwargs.get("chart_types", ["all"])

        try:
            charts = {}

            risk_analysis = report_data.get("risk_analysis", {})
            compliance_analysis = report_data.get("compliance_analysis", {})
            clause_analysis = report_data.get("clause_analysis", {})
            overall_score = report_data.get("overall_score", 0)

            if "all" in chart_types or "risk_pie" in chart_types:
                charts["risk_pie"] = self._risk_pie_chart(risk_analysis)

            if "all" in chart_types or "risk_bar" in chart_types:
                charts["risk_bar"] = self._risk_bar_chart(risk_analysis)

            if "all" in chart_types or "compliance_radar" in chart_types:
                charts["compliance_radar"] = self._compliance_radar_chart(compliance_analysis)

            if "all" in chart_types or "completeness_progress" in chart_types:
                charts["completeness_progress"] = self._completeness_progress(clause_analysis)

            if "all" in chart_types or "score_gauge" in chart_types:
                charts["score_gauge"] = self._score_gauge(overall_score)

            if "all" in chart_types or "issue_heatmap" in chart_types:
                charts["issue_heatmap"] = self._issue_heatmap(risk_analysis, compliance_analysis, clause_analysis)

            return {
                "charts": charts,
                "chart_count": len(charts),
                "format": "json",
            }
        except Exception as e:
            logger.error(f"可视化数据生成失败: {e}")
            return {"error": str(e)}

    def _risk_pie_chart(self, risk_analysis: Dict) -> Dict:
        distribution = risk_analysis.get("distribution", {"high": 0, "medium": 0, "low": 0})
        return {
            "type": "pie",
            "title": "风险分布",
            "data": [
                {"label": "高风险", "value": distribution.get("high", 0), "color": "#e74c3c"},
                {"label": "中风险", "value": distribution.get("medium", 0), "color": "#f39c12"},
                {"label": "低风险", "value": distribution.get("low", 0), "color": "#27ae60"},
            ],
            "total": sum(distribution.values()),
        }

    def _risk_bar_chart(self, risk_analysis: Dict) -> Dict:
        risks = risk_analysis.get("risks", [])
        categories: Dict[str, int] = {}
        for risk in risks:
            cat = risk.get("category", "其他")
            categories[cat] = categories.get(cat, 0) + 1
        category_labels = {
            "liability": "责任", "payment": "付款", "ip": "知识产权",
            "confidentiality": "保密", "termination": "终止",
            "dispute": "争议", "compliance": "合规", "other": "其他",
        }
        return {
            "type": "bar",
            "title": "风险类别分布",
            "data": [
                {"label": category_labels.get(k, k), "value": v}
                for k, v in sorted(categories.items(), key=lambda x: -x[1])
            ],
        }

    def _compliance_radar_chart(self, compliance_analysis: Dict) -> Dict:
        violations = compliance_analysis.get("violations", [])
        missing = compliance_analysis.get("missing_clauses", [])
        score = compliance_analysis.get("score", 0)
        dimensions = [
            {"label": "合规得分", "value": score, "max": 100},
            {"label": "违规项", "value": max(0, 100 - len(violations) * 20), "max": 100},
            {"label": "必备条款", "value": max(0, 100 - len(missing) * 25), "max": 100},
            {"label": "完整性", "value": compliance_analysis.get("status", "unknown") == "compliant" and 90 or 60, "max": 100},
        ]
        return {
            "type": "radar",
            "title": "合规性评估",
            "dimensions": dimensions,
        }

    def _completeness_progress(self, clause_analysis: Dict) -> Dict:
        completeness_score = clause_analysis.get("completeness_score", 0)
        missing = clause_analysis.get("missing_clauses", [])
        return {
            "type": "progress",
            "title": "条款完整性",
            "value": round(completeness_score * 100),
            "max": 100,
            "missing_items": missing,
        }

    def _score_gauge(self, overall_score: int) -> Dict:
        if overall_score >= 80:
            level, color = "良好", "#27ae60"
        elif overall_score >= 60:
            level, color = "一般", "#f39c12"
        elif overall_score >= 40:
            level, color = "较差", "#e67e22"
        else:
            level, color = "危险", "#e74c3c"
        return {
            "type": "gauge",
            "title": "综合评分",
            "value": overall_score,
            "max": 100,
            "level": level,
            "color": color,
        }

    def _issue_heatmap(
        self,
        risk_analysis: Dict,
        compliance_analysis: Dict,
        clause_analysis: Dict,
    ) -> Dict:
        categories = ["责任", "付款", "知识产权", "保密", "终止", "争议", "合规", "条款"]
        values = [
            risk_analysis.get("distribution", {}).get("high", 0) + risk_analysis.get("distribution", {}).get("medium", 0),
            len([r for r in risk_analysis.get("risks", []) if r.get("category") == "payment"]),
            len([r for r in risk_analysis.get("risks", []) if r.get("category") == "ip"]),
            len([r for r in risk_analysis.get("risks", []) if r.get("category") == "confidentiality"]),
            len([r for r in risk_analysis.get("risks", []) if r.get("category") == "termination"]),
            len([r for r in risk_analysis.get("risks", []) if r.get("category") == "dispute"]),
            compliance_analysis.get("violations_count", 0),
            clause_analysis.get("issues_count", 0),
        ]
        return {
            "type": "heatmap",
            "title": "问题热力图",
            "data": [{"category": c, "count": v} for c, v in zip(categories, values)],
        }
