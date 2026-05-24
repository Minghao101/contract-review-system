"""
风险评估Agent模块 - 负责评估合同风险
"""
from typing import Any, Dict, List, Optional
import re
import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RiskAssessmentAgent(BaseAgent):
    """
    风险评估Agent

    职责：
    - 识别合同风险点
    - 评估风险等级
    - 生成风险报告
    - 提供改进建议
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

        # 风险规则库
        self._risk_rules = [
            {
                "id": "R001",
                "name": "无限责任风险",
                "pattern": r"无限责任|承担一切.*责任|全部损失",
                "severity": "high",
                "category": "liability",
                "suggestion": "建议将无限责任改为有限责任，明确责任上限"
            },
            {
                "id": "R002",
                "name": "单方面解除权风险",
                "pattern": r"单方面?解除|随时解除|无需.*同意",
                "severity": "high",
                "category": "termination",
                "suggestion": "建议增加提前通知期和合理解除条件"
            },
            {
                "id": "R003",
                "name": "自动续约风险",
                "pattern": r"自动续约|自动延长",
                "severity": "medium",
                "category": "renewal",
                "suggestion": "建议设置续约需双方书面确认"
            },
            {
                "id": "R004",
                "name": "管辖权风险",
                "pattern": r"由.*法院管辖|仲裁条款",
                "severity": "low",
                "category": "dispute",
                "suggestion": "确认管辖权约定是否对己方有利"
            },
            {
                "id": "R005",
                "name": "知识产权归属不明确",
                "pattern": r"知识产权.*归属|成果归属",
                "severity": "medium",
                "category": "ip",
                "suggestion": "建议明确约定知识产权归属和使用权限"
            },
            {
                "id": "R006",
                "name": "保密期限过长",
                "pattern": r"永久保密|保密期限.*无限",
                "severity": "medium",
                "category": "confidentiality",
                "suggestion": "建议设置合理的保密期限（通常2-5年）"
            },
            {
                "id": "R007",
                "name": "违约金过高",
                "pattern": r"违约金.*[0-9]+%|[0-9]+倍违约金",
                "severity": "high",
                "category": "penalty",
                "suggestion": "建议将违约金调整为合理范围（通常不超过合同金额的30%）"
            },
            {
                "id": "R008",
                "name": "付款条件不利",
                "pattern": r"预付.*全款|先款后货",
                "severity": "medium",
                "category": "payment",
                "suggestion": "建议采用分期付款或增加验收后付款条款"
            },
            {
                "id": "R009",
                "name": "不可抗力条款缺失",
                "pattern": r"不可抗力",
                "severity": "low",
                "category": "force_majeure",
                "suggestion": "检查不可抗力条款是否完善"
            },
            {
                "id": "R010",
                "name": "争议解决方式不明确",
                "pattern": r"争议.*解决|纠纷.*处理",
                "severity": "low",
                "category": "dispute",
                "suggestion": "建议明确约定争议解决方式（仲裁或诉讼）"
            },
        ]

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

        # 1. 应用风险规则
        detected_risks = self._apply_risk_rules(contract_text)

        # 2. 评估风险等级
        risk_level = self._calculate_risk_level(detected_risks)

        # 3. 分析特定领域风险
        domain_risks = self._analyze_domain_risks(contract_text, contract_type)

        # 4. 合并风险
        all_risks = detected_risks + domain_risks

        # 5. 生成建议
        recommendations = self._generate_recommendations(all_risks)

        # 6. 生成风险摘要
        risk_summary = self._generate_risk_summary(all_risks, risk_level)

        result = {
            "risk_level": risk_level,
            "risks": all_risks,
            "recommendations": recommendations,
            "summary": risk_summary,
            "risk_statistics": {
                "total": len(all_risks),
                "high": len([r for r in all_risks if r.get("severity") == "high"]),
                "medium": len([r for r in all_risks if r.get("severity") == "medium"]),
                "low": len([r for r in all_risks if r.get("severity") == "low"]),
            }
        }

        logger.info(f"风险评估完成，风险等级: {risk_level}，发现风险: {len(all_risks)}个")
        return result

    def _apply_risk_rules(self, text: str) -> List[Dict[str, Any]]:
        """
        应用风险规则检测风险

        Args:
            text: 合同文本

        Returns:
            检测到的风险列表
        """
        risks = []

        for rule in self._risk_rules:
            pattern = rule["pattern"]
            matches = list(re.finditer(pattern, text, re.IGNORECASE))

            if matches:
                for match in matches:
                    # 获取匹配内容的上下文
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    context = text[start:end].replace("\n", " ")

                    risks.append({
                        "rule_id": rule["id"],
                        "name": rule["name"],
                        "severity": rule["severity"],
                        "category": rule["category"],
                        "matched_content": match.group(0),
                        "context": f"...{context}...",
                        "position": match.start(),
                        "suggestion": rule["suggestion"],
                    })

        return risks

    def _calculate_risk_level(self, risks: List[Dict[str, Any]]) -> str:
        """
        计算整体风险等级

        Args:
            risks: 风险列表

        Returns:
            风险等级: low/medium/high/critical
        """
        if not risks:
            return "low"

        # 计算风险分数
        severity_scores = {"high": 3, "medium": 2, "low": 1}
        total_score = sum(
            severity_scores.get(r.get("severity", "low"), 1)
            for r in risks
        )

        # 根据分数确定风险等级
        if total_score >= 10:
            return "critical"
        elif total_score >= 6:
            return "high"
        elif total_score >= 3:
            return "medium"
        else:
            return "low"

    def _analyze_domain_risks(
        self,
        text: str,
        contract_type: str
    ) -> List[Dict[str, Any]]:
        """
        分析特定领域风险

        Args:
            text: 合同文本
            contract_type: 合同类型

        Returns:
            特定领域风险列表
        """
        domain_risks = []

        # 通用领域风险检查
        domain_checks = [
            {
                "name": "合同金额与支付条款风险",
                "pattern": r"总价.*[0-9]|金额.*[0-9]",
                "check_func": self._check_payment_terms,
                "severity": "medium",
                "category": "financial"
            },
            {
                "name": "交付时间风险",
                "pattern": r"交付.*时间|完成.*期限",
                "check_func": self._check_delivery_terms,
                "severity": "medium",
                "category": "delivery"
            },
            {
                "name": "质量标准风险",
                "pattern": r"质量.*标准|验收.*标准",
                "check_func": self._check_quality_terms,
                "severity": "medium",
                "category": "quality"
            },
        ]

        for check in domain_checks:
            if re.search(check["pattern"], text):
                # 执行特定检查
                check_result = check["check_func"](text)
                if check_result:
                    domain_risks.append({
                        "name": check["name"],
                        "severity": check["severity"],
                        "category": check["category"],
                        "details": check_result,
                        "suggestion": f"建议审查{check['name']}"
                    })

        return domain_risks

    def _check_payment_terms(self, text: str) -> Optional[str]:
        """检查支付条款"""
        # 检查是否有明确的付款时间
        if "预付" in text and "全款" in text:
            return "存在预付全款条款，可能增加财务风险"
        return None

    def _check_delivery_terms(self, text: str) -> Optional[str]:
        """检查交付条款"""
        # 检查是否有明确的交付时间
        if "尽快" in text or "及时" in text:
            return "交付时间表述不够明确"
        return None

    def _check_quality_terms(self, text: str) -> Optional[str]:
        """检查质量条款"""
        # 检查是否有明确的质量标准
        if "合理" in text and "质量" in text:
            return "质量标准表述可能不够具体"
        return None

    def _generate_recommendations(self, risks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成改进建议

        Args:
            risks: 风险列表

        Returns:
            建议列表
        """
        recommendations = []

        # 按风险等级排序
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_risks = sorted(
            risks,
            key=lambda x: severity_order.get(x.get("severity", "low"), 3)
        )

        # 为每个风险生成建议
        for risk in sorted_risks:
            recommendations.append({
                "risk_name": risk.get("name"),
                "severity": risk.get("severity"),
                "suggestion": risk.get("suggestion", "建议审查相关条款"),
                "priority": "high" if risk.get("severity") == "high" else "medium",
            })

        # 添加通用建议
        if len(risks) > 3:
            recommendations.append({
                "risk_name": "整体风险",
                "severity": "high",
                "suggestion": "合同存在多个风险点，建议由专业法律人员进行详细审查",
                "priority": "high",
            })

        return recommendations

    def _generate_risk_summary(
        self,
        risks: List[Dict[str, Any]],
        risk_level: str
    ) -> Dict[str, Any]:
        """
        生成风险摘要

        Args:
            risks: 风险列表
            risk_level: 风险等级

        Returns:
            风险摘要
        """
        # 按类别统计
        category_stats = {}
        for risk in risks:
            category = risk.get("category", "other")
            if category not in category_stats:
                category_stats[category] = 0
            category_stats[category] += 1

        # 生成摘要文本
        summary_text = f"整体风险等级: {risk_level.upper()}\n"
        summary_text += f"共发现 {len(risks)} 个风险点\n"

        if category_stats:
            summary_text += "风险分布: "
            summary_text += ", ".join(
                f"{cat}: {count}个"
                for cat, count in category_stats.items()
            )

        return {
            "risk_level": risk_level,
            "total_risks": len(risks),
            "category_distribution": category_stats,
            "summary_text": summary_text,
        }
