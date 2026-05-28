"""
综合报告生成Skill - 汇总所有分析结果生成结构化报告
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class ReportGeneratorSkill(BaseSkill):
    """
    综合报告生成Skill

    功能：
    - 汇总文档解析、条款分析、风险评估、合规检查结果
    - 生成结构化的审查报告
    - 提供执行摘要和结论
    """

    def __init__(self):
        super().__init__(
            skill_id="report_generator",
            name="综合报告生成",
            description="汇总所有分析结果，生成结构化的合同审查报告",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        生成综合审查报告

        Args:
            **kwargs:
                - document_info: 文档解析结果（可选）
                - clause_analysis: 条款分析结果（可选）
                - risk_assessment: 风险评估结果（可选）
                - compliance_check: 合规检查结果（可选）
                - contract_type: 合同类型（可选）

        Returns:
            结构化报告
        """
        document_info = kwargs.get("document_info", {})
        clause_analysis = kwargs.get("clause_analysis", {})
        risk_assessment = kwargs.get("risk_assessment", {})
        compliance_check = kwargs.get("compliance_check", {})
        contract_type = kwargs.get("contract_type", "general")

        try:
            # 1. 生成执行摘要
            executive_summary = self._generate_executive_summary(
                document_info, clause_analysis, risk_assessment, compliance_check
            )

            # 2. 风险分析
            risk_section = self._analyze_risks(risk_assessment)

            # 3. 合规分析
            compliance_section = self._analyze_compliance(compliance_check)

            # 4. 条款分析
            clause_section = self._analyze_clauses(clause_analysis)

            # 5. 生成建议
            recommendations = self._generate_recommendations(
                risk_assessment, compliance_check, clause_analysis
            )

            # 6. 结论
            conclusion = self._generate_conclusion(
                risk_section, compliance_section, clause_section
            )

            # 7. 评分
            overall_score = self._calculate_overall_score(
                risk_section, compliance_section, clause_section
            )

            report = {
                "report": {
                    "title": "合同审查报告",
                    "generated_at": datetime.now().isoformat(),
                    "contract_type": contract_type,
                    "executive_summary": executive_summary,
                    "document_overview": document_info,
                    "risk_analysis": risk_section,
                    "compliance_analysis": compliance_section,
                    "clause_analysis": clause_section,
                    "recommendations": recommendations,
                    "conclusion": conclusion,
                },
                "overall_score": overall_score,
                "summary": {
                    "risk_level": risk_section.get("overall_level", "unknown"),
                    "compliance_score": compliance_section.get("score", 0),
                    "completeness_score": clause_section.get("completeness_score", 0),
                    "total_issues": (
                        risk_section.get("total_risks", 0)
                        + compliance_section.get("violations_count", 0)
                        + clause_section.get("issues_count", 0)
                    ),
                    "verdict": conclusion.get("verdict", "需要人工审查"),
                },
                "visualization": {
                    "risk_distribution": risk_section.get("distribution", {}),
                    "compliance_bar": compliance_section.get("score", 0),
                    "completeness_bar": clause_section.get("completeness_score", 0),
                    "overall_score": overall_score,
                },
            }

            return report
        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return {"error": str(e)}

    def _generate_executive_summary(
        self,
        document_info: Dict,
        clause_analysis: Dict,
        risk_assessment: Dict,
        compliance_check: Dict,
    ) -> str:
        """生成执行摘要"""
        parts = []

        # 文档概况
        contract_type = document_info.get("contract_type", "未知类型")
        parties = document_info.get("parties", [])
        parties_str = "、".join(parties) if parties else "未知当事人"
        parts.append(f"本报告针对一份{contract_type}合同进行审查，合同当事人为{parties_str}。")

        # 风险概况
        risk_level = risk_assessment.get("risk_level", "unknown")
        total_risks = risk_assessment.get("total_risks", len(risk_assessment.get("risks", [])))
        risk_level_cn = {"low": "低", "medium": "中等", "high": "高", "critical": "极高"}.get(risk_level, "未知")
        if total_risks > 0:
            parts.append(f"经审查，发现{total_risks}项风险，整体风险等级为{risk_level_cn}。")
        else:
            parts.append("未发现明显风险。")

        # 合规概况
        compliance_score = compliance_check.get("score", 0)
        if compliance_score > 0:
            parts.append(f"合规检查得分{compliance_score}分。")

        return "".join(parts)

    def _analyze_risks(self, risk_assessment: Dict) -> Dict[str, Any]:
        """分析风险"""
        risks = risk_assessment.get("risks", [])
        risk_level = risk_assessment.get("risk_level", "unknown")

        distribution = {"high": 0, "medium": 0, "low": 0}
        for risk in risks:
            sev = risk.get("severity", "low")
            distribution[sev] = distribution.get(sev, 0) + 1

        return {
            "overall_level": risk_level,
            "total_risks": len(risks),
            "distribution": distribution,
            "risks": risks,
        }

    def _analyze_compliance(self, compliance_check: Dict) -> Dict[str, Any]:
        """分析合规"""
        return {
            "score": compliance_check.get("score", 0),
            "status": compliance_check.get("compliance_status", "unknown"),
            "violations_count": len(compliance_check.get("compliance_violations", [])),
            "missing_count": len(compliance_check.get("missing_clauses", [])),
            "violations": compliance_check.get("compliance_violations", []),
            "missing_clauses": compliance_check.get("missing_clauses", []),
        }

    def _analyze_clauses(self, clause_analysis: Dict) -> Dict[str, Any]:
        """分析条款"""
        completeness = clause_analysis.get("analysis", {}).get("completeness", {})
        issues = clause_analysis.get("issues", [])

        return {
            "completeness_score": completeness.get("completeness_score", 0),
            "missing_clauses": completeness.get("missing_clauses", []),
            "issues_count": len(issues),
            "issues": issues,
            "rights_obligations": clause_analysis.get("analysis", {}).get("rights_obligations", {}),
        }

    def _generate_recommendations(
        self,
        risk_assessment: Dict,
        compliance_check: Dict,
        clause_analysis: Dict,
    ) -> List[Dict[str, Any]]:
        """生成建议"""
        recommendations = []

        # 风险建议
        for risk in risk_assessment.get("risks", []):
            if risk.get("severity") in ("high", "medium"):
                recommendations.append({
                    "priority": risk.get("severity", "medium"),
                    "category": "风险",
                    "content": f"{risk.get('name', '风险')}: {risk.get('suggestion', '建议修改')}",
                })

        # 合规建议
        for v in compliance_check.get("compliance_violations", []):
            recommendations.append({
                "priority": v.get("severity", "medium"),
                "category": "合规",
                "content": f"{v.get('regulation', '法规')}: {v.get('suggestion', '建议修改')}",
            })

        # 条款建议
        for issue in clause_analysis.get("issues", []):
            if issue.get("severity") in ("high", "medium"):
                recommendations.append({
                    "priority": issue.get("severity", "medium"),
                    "category": "条款",
                    "content": issue.get("suggestion", "建议修改"),
                })

        # 排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 2))

        return recommendations

    def _generate_conclusion(
        self,
        risk_section: Dict,
        compliance_section: Dict,
        clause_section: Dict,
    ) -> Dict[str, Any]:
        """生成结论"""
        risk_level = risk_section.get("overall_level", "unknown")
        compliance_score = compliance_section.get("score", 0)
        completeness = clause_section.get("completeness_score", 0)

        # 决策逻辑
        if risk_level in ("critical", "high"):
            verdict = "不建议签署"
            reason = "合同存在高风险条款，建议大幅修改后再签署"
        elif risk_level == "medium" or compliance_score < 60:
            verdict = "建议修改后签署"
            reason = "合同存在中等风险或合规问题，建议修改相关条款后签署"
        elif completeness < 0.6:
            verdict = "建议补充条款后签署"
            reason = "合同必备条款不完整，建议补充后签署"
        else:
            verdict = "建议签署"
            reason = "合同整体风险可控，合规性良好"

        return {
            "verdict": verdict,
            "reason": reason,
            "risk_level": risk_level,
            "compliance_score": compliance_score,
            "completeness_score": completeness,
        }

    def _calculate_overall_score(
        self,
        risk_section: Dict,
        compliance_section: Dict,
        clause_section: Dict,
    ) -> int:
        """计算综合评分（0-100，越高越好）"""
        # 风险分数（风险越低分数越高）
        risk_scores = {"low": 90, "medium": 60, "high": 30, "critical": 10}
        risk_score = risk_scores.get(risk_section.get("overall_level", "medium"), 50)

        # 合规分数
        compliance_score = compliance_section.get("score", 50)

        # 完整性分数
        completeness_score = int(clause_section.get("completeness_score", 0.5) * 100)

        # 加权平均
        overall = int(risk_score * 0.4 + compliance_score * 0.35 + completeness_score * 0.25)
        return min(100, max(0, overall))
