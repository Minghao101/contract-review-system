"""
报告生成Agent模块 - 负责生成审查报告
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ReportGeneratorAgent(BaseAgent):
    """
    报告生成Agent

    职责：
    - 汇总各阶段分析结果
    - 生成结构化审查报告
    - 提供可视化数据
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

        # 1. 提取各阶段结果
        document_info = previous_results.get("parse_document", {}).get("result", {})
        clause_analysis = previous_results.get("analyze_clauses", {}).get("result", {})
        risk_assessment = previous_results.get("assess_risks", {}).get("result", {})

        # 2. 生成报告
        report = self._generate_report(
            document_info,
            clause_analysis,
            risk_assessment
        )

        # 3. 生成摘要
        summary = self._generate_summary(
            document_info,
            clause_analysis,
            risk_assessment
        )

        # 4. 生成可视化数据
        visualization = self._generate_visualization(
            clause_analysis,
            risk_assessment
        )

        result = {
            "report": report,
            "summary": summary,
            "visualization": visualization,
            "generated_at": datetime.now().isoformat(),
        }

        logger.info("审查报告生成完成")
        return result

    def _generate_report(
        self,
        document_info: Dict[str, Any],
        clause_analysis: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成完整报告

        Args:
            document_info: 文档信息
            clause_analysis: 条款分析结果
            risk_assessment: 风险评估结果

        Returns:
            报告内容
        """
        # 提取信息
        doc_info = document_info.get("document_info", {})
        contract_type = doc_info.get("contract_type", "general")
        completeness = clause_analysis.get("analysis", {}).get("completeness", {})
        risks = risk_assessment.get("risks", [])
        recommendations = risk_assessment.get("recommendations", [])
        risk_level = risk_assessment.get("risk_level", "unknown")

        # 生成报告各部分
        report = {
            "title": "合同审查报告",
            "generated_at": datetime.now().isoformat(),
            "executive_summary": self._generate_executive_summary(
                contract_type, risk_level, len(risks)
            ),
            "document_overview": {
                "contract_type": contract_type,
                "text_length": doc_info.get("text_length", 0),
                "sections_count": doc_info.get("sections_count", 0),
            },
            "completeness_analysis": {
                "score": completeness.get("completeness_score", 0),
                "found_clauses": completeness.get("found", []),
                "missing_clauses": completeness.get("missing", []),
            },
            "risk_assessment": {
                "overall_level": risk_level,
                "total_risks": len(risks),
                "high_risks": len([r for r in risks if r.get("severity") == "high"]),
                "medium_risks": len([r for r in risks if r.get("severity") == "medium"]),
                "low_risks": len([r for r in risks if r.get("severity") == "low"]),
                "details": risks,
            },
            "recommendations": recommendations,
            "conclusion": self._generate_conclusion(risk_level, len(risks)),
        }

        return report

    def _generate_executive_summary(
        self,
        contract_type: str,
        risk_level: str,
        risk_count: int
    ) -> str:
        """生成执行摘要"""
        type_names = {
            "sales": "销售合同",
            "service": "服务合同",
            "lease": "租赁合同",
            "labor": "劳动合同",
            "nda": "保密协议",
            "general": "一般合同",
        }

        type_name = type_names.get(contract_type, "合同")

        level_descriptions = {
            "low": "整体风险较低",
            "medium": "存在一些需要关注的风险点",
            "high": "存在较高风险，建议谨慎签署",
            "critical": "存在严重风险，强烈建议修改后再签署",
        }

        summary = f"本报告针对一份{type_name}进行了全面审查。"
        summary += f"经过分析，{level_descriptions.get(risk_level, '无法确定风险等级')}。"
        summary += f"共发现 {risk_count} 个风险点需要关注。"

        return summary

    def _generate_conclusion(self, risk_level: str, risk_count: int) -> Dict[str, Any]:
        """生成结论"""
        conclusions = {
            "low": {
                "verdict": "建议签署",
                "description": "合同条款较为完善，风险可控，建议在签署前再次确认关键条款。",
            },
            "medium": {
                "verdict": "建议修改后签署",
                "description": "合同存在一些风险点，建议在签署前与对方协商修改相关条款。",
            },
            "high": {
                "verdict": "建议大幅修改",
                "description": "合同存在较高风险，建议由专业法律人员审核并进行大幅修改。",
            },
            "critical": {
                "verdict": "不建议签署",
                "description": "合同存在严重风险，强烈建议重新谈判或放弃签署。",
            },
        }

        conclusion = conclusions.get(risk_level, conclusions["medium"])

        return {
            "verdict": conclusion["verdict"],
            "description": conclusion["description"],
            "risk_level": risk_level,
            "risk_count": risk_count,
        }

    def _generate_summary(
        self,
        document_info: Dict[str, Any],
        clause_analysis: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成摘要

        Args:
            document_info: 文档信息
            clause_analysis: 条款分析结果
            risk_assessment: 风险评估结果

        Returns:
            摘要内容
        """
        doc_info = document_info.get("document_info", {})
        completeness = clause_analysis.get("analysis", {}).get("completeness", {})
        risk_level = risk_assessment.get("risk_level", "unknown")
        risks = risk_assessment.get("risks", [])

        return {
            "contract_type": doc_info.get("contract_type", "general"),
            "completeness_score": completeness.get("completeness_score", 0),
            "risk_level": risk_level,
            "total_risks": len(risks),
            "missing_clauses": len(completeness.get("missing", [])),
            "recommendations_count": len(risk_assessment.get("recommendations", [])),
        }

    def _generate_visualization(
        self,
        clause_analysis: Dict[str, Any],
        risk_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成可视化数据

        Args:
            clause_analysis: 条款分析结果
            risk_assessment: 风险评估结果

        Returns:
            可视化数据
        """
        risks = risk_assessment.get("risks", [])

        # 风险分布数据
        risk_distribution = {
            "high": len([r for r in risks if r.get("severity") == "high"]),
            "medium": len([r for r in risks if r.get("severity") == "medium"]),
            "low": len([r for r in risks if r.get("severity") == "low"]),
        }

        # 风险类别数据
        risk_categories = {}
        for risk in risks:
            category = risk.get("category", "other")
            if category not in risk_categories:
                risk_categories[category] = 0
            risk_categories[category] += 1

        # 完整性数据
        completeness = clause_analysis.get("analysis", {}).get("completeness", {})
        completeness_data = {
            "found": len(completeness.get("found", [])),
            "missing": len(completeness.get("missing", [])),
        }

        return {
            "risk_distribution": risk_distribution,
            "risk_categories": risk_categories,
            "completeness_data": completeness_data,
        }
