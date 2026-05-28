"""
风险识别Skill - 识别合同中的潜在风险
"""
from typing import Any, Dict, List
import re
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class RiskIdentifierSkill(BaseSkill):
    """
    风险识别Skill

    功能：
    - 基于规则库识别合同风险
    - 支持多类别风险检测
    - 提供风险位置定位
    """

    # 风险规则库
    RISK_RULES = [
        # 责任风险
        {"id": "unlimited_liability", "name": "无限责任风险", "category": "liability", "severity": "high",
         "pattern": r"无限责任|承担一切.*责任|对.*一切.*后果.*负责",
         "description": "合同约定了无限责任，可能导致承担超出预期的赔偿",
         "suggestion": "建议设置责任上限，明确赔偿范围"},
        {"id": "joint_liability", "name": "连带责任风险", "category": "liability", "severity": "medium",
         "pattern": r"连带责任|承担连带",
         "description": "连带责任可能扩大赔偿范围",
         "suggestion": "建议明确连带责任的适用条件和范围"},

        # 付款风险
        {"id": "payment_advance", "name": "预付款风险", "category": "payment", "severity": "medium",
         "pattern": r"预付.*100%|全额预付|一次性付清",
         "description": "预付款比例过高，资金风险大",
         "suggestion": "建议分期付款，设置付款节点和验收条件"},
        {"id": "payment_penalty_high", "name": "逾期付款违约金过高", "category": "payment", "severity": "medium",
         "pattern": r"逾期.*违约金.*?(\d{2,})\s*%|每日.*罚息.*?(\d{2,})\s*%",
         "description": "逾期付款违约金比例可能过高",
         "suggestion": "建议违约金不超过日万分之五"},
        {"id": "payment_vague", "name": "付款条件模糊", "category": "payment", "severity": "medium",
         "pattern": r"适时付款|必要时付款|按需付款",
         "description": "付款条件不明确，容易产生争议",
         "suggestion": "建议明确付款时间、方式和条件"},

        # 知识产权风险
        {"id": "ip_all归属", "name": "知识产权归属不清", "category": "ip", "severity": "high",
         "pattern": r"所有.*成果.*归.*甲方|一切.*知识产权.*归.*甲方",
         "description": "知识产权全部归属一方，可能不合理",
         "suggestion": "建议明确区分职务作品和委托作品，合理约定归属"},
        {"id": "ip_broad_scope", "name": "知识产权范围过宽", "category": "ip", "severity": "medium",
         "pattern": r"包括但不限于.*所有.*知识产权|全部.*衍生.*权利",
         "description": "知识产权约定范围过宽",
         "suggestion": "建议明确约定知识产权的具体范围"},

        # 保密风险
        {"id": "confidentiality_permanent", "name": "保密期限过长", "category": "confidentiality", "severity": "medium",
         "pattern": r"永久保密|保密期.*无限|终身保密",
         "description": "保密期限过长或无期限，不合理",
         "suggestion": "建议设定合理保密期限（一般2-5年）"},
        {"id": "confidentiality_broad", "name": "保密范围过宽", "category": "confidentiality", "severity": "low",
         "pattern": r"所有.*信息.*均为保密|一切.*信息.*保密",
         "description": "保密范围界定过宽",
         "suggestion": "建议明确界定保密信息的具体范围"},

        # 终止风险
        {"id": "termination_unilateral", "name": "单方解除权不对等", "category": "termination", "severity": "high",
         "pattern": r"甲方.*可随时.*解除[^乙方]*乙方.*不得.*解除",
         "description": "解除权不对等，一方可随时解除而另一方不能",
         "suggestion": "建议双方解除权对等，或明确不对等的合理理由"},
        {"id": "auto_renewal", "name": "自动续约风险", "category": "termination", "severity": "medium",
         "pattern": r"自动续约|自动延长.*除非.*提前.*通知",
         "description": "自动续约可能导致合同无限延续",
         "suggestion": "建议设置自动续约的次数上限和提前通知期"},

        # 争议解决风险
        {"id": "dispute_no_mechanism", "name": "争议解决机制缺失", "category": "dispute", "severity": "high",
         "pattern": None,  # 特殊检测：检查是否缺少争议解决条款
         "description": "合同未约定争议解决方式",
         "suggestion": "建议明确约定仲裁或诉讼作为争议解决方式"},
        {"id": "dispute_both", "name": "仲裁诉讼并存", "category": "dispute", "severity": "medium",
         "pattern": r"仲裁.*诉讼|诉讼.*仲裁",
         "description": "同时约定仲裁和诉讼，仲裁条款可能无效",
         "suggestion": "建议选择仲裁或诉讼中的一种"},

        # 不可抗力风险
        {"id": "no_force_majeure", "name": "缺少不可抗力条款", "category": "other", "severity": "medium",
         "pattern": None,  # 特殊检测
         "description": "合同未约定不可抗力条款",
         "suggestion": "建议增加不可抗力条款，明确免责范围"},

        # 期限风险
        {"id": "deadline_tight", "name": "履约期限过紧", "category": "other", "severity": "medium",
         "pattern": r"(\d+)\s*天内.*完成.*(?:全部|所有).*(?:工作|任务|交付)",
         "description": "履约期限可能过紧，执行难度大",
         "suggestion": "建议评估实际履约能力，合理设置期限"},
    ]

    def __init__(self):
        super().__init__(
            skill_id="risk_identifier",
            name="风险识别",
            description="基于规则库识别合同中的潜在风险点",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行风险识别

        Args:
            **kwargs:
                - text: 合同文本（必填）
                - categories: 指定风险类别列表（可选）

        Returns:
            风险识别结果
        """
        text = kwargs.get("text", "")
        categories = kwargs.get("categories", [])

        if not text:
            return {"error": "请提供合同文本"}

        try:
            # 1. 规则匹配
            risks = self._match_risks(text, categories)

            # 2. 特殊检测（缺失条款）
            special_risks = self._check_special_cases(text)
            risks.extend(special_risks)

            # 3. 统计
            severity_count = {"high": 0, "medium": 0, "low": 0}
            category_count = {}
            for risk in risks:
                severity_count[risk["severity"]] = severity_count.get(risk["severity"], 0) + 1
                cat = risk["category"]
                category_count[cat] = category_count.get(cat, 0) + 1

            return {
                "total_risks": len(risks),
                "risks": risks,
                "severity_distribution": severity_count,
                "category_distribution": category_count,
            }
        except Exception as e:
            logger.error(f"风险识别失败: {e}")
            return {"error": str(e)}

    def _match_risks(self, text: str, categories: List[str]) -> List[Dict[str, Any]]:
        """规则匹配"""
        risks = []
        for rule in self.RISK_RULES:
            if rule["pattern"] is None:
                continue
            if categories and rule["category"] not in categories:
                continue

            matches = list(re.finditer(rule["pattern"], text))
            for match in matches:
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                context = text[start:end].replace("\n", " ")

                risks.append({
                    "risk_id": rule["id"],
                    "name": rule["name"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "suggestion": rule["suggestion"],
                    "matched_text": match.group(0),
                    "context": context,
                })
        return risks

    def _check_special_cases(self, text: str) -> List[Dict[str, Any]]:
        """特殊风险检测"""
        special_risks = []

        # 检查是否缺少争议解决条款
        dispute_keywords = ["争议", "纠纷", "仲裁", "诉讼", "管辖"]
        if not any(kw in text for kw in dispute_keywords):
            special_risks.append({
                "risk_id": "dispute_no_mechanism",
                "name": "争议解决机制缺失",
                "category": "dispute",
                "severity": "high",
                "description": "合同未约定争议解决方式",
                "suggestion": "建议明确约定仲裁或诉讼作为争议解决方式",
                "matched_text": "",
                "context": "全文未找到争议解决相关条款",
            })

        # 检查是否缺少不可抗力条款
        force_majeure_keywords = ["不可抗力", "自然灾害", "政府行为", "社会事件"]
        if not any(kw in text for kw in force_majeure_keywords):
            special_risks.append({
                "risk_id": "no_force_majeure",
                "name": "缺少不可抗力条款",
                "category": "other",
                "severity": "medium",
                "description": "合同未约定不可抗力条款",
                "suggestion": "建议增加不可抗力条款，明确免责范围",
                "matched_text": "",
                "context": "全文未找到不可抗力相关条款",
            })

        return special_risks
