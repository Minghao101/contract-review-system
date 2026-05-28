"""
风险缓解Skill - 为识别出的风险生成缓解建议
"""
from typing import Any, Dict, List
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class MitigationSuggesterSkill(BaseSkill):
    """
    风险缓解Skill

    功能：
    - 根据风险类型生成具体缓解措施
    - 按优先级排序建议
    - 提供条款修改模板
    """

    # 缓解建议模板库
    MITIGATION_TEMPLATES = {
        # 责任风险
        "unlimited_liability": {
            "mitigation": "建议在合同中增加责任上限条款",
            "clause_template": "任何一方承担的赔偿责任总额不超过本合同总金额的【X】倍。",
            "priority": "high",
            "effort": "low",
        },
        "joint_liability": {
            "mitigation": "建议明确连带责任的适用条件和限额",
            "clause_template": "连带责任仅适用于因故意或重大过失造成的损失，且每方承担的赔偿责任不超过其在本合同中的获利金额。",
            "priority": "medium",
            "effort": "low",
        },

        # 付款风险
        "payment_advance": {
            "mitigation": "建议调整为分期付款，设置验收节点",
            "clause_template": "合同签订后支付【30】%预付款，验收合格后支付【60】%，质保期满后支付【10】%尾款。",
            "priority": "medium",
            "effort": "medium",
        },
        "payment_penalty_high": {
            "mitigation": "建议将违约金调整为合理比例",
            "clause_template": "逾期付款的，每日按逾期金额的万分之【五】支付违约金，累计不超过逾期金额的【30】%。",
            "priority": "medium",
            "effort": "low",
        },
        "payment_vague": {
            "mitigation": "建议明确付款时间、方式和条件",
            "clause_template": "甲方应在收到乙方发票后【30】个工作日内，通过银行转账方式支付款项至乙方指定账户。",
            "priority": "high",
            "effort": "low",
        },

        # 知识产权风险
        "ip_all归属": {
            "mitigation": "建议合理约定知识产权归属，区分背景IP和 foreground IP",
            "clause_template": "双方各自保留其在签订本合同前已拥有的知识产权。本合同履行过程中产生的新知识产权，由【创造方】所有，另一方享有免费使用权。",
            "priority": "high",
            "effort": "medium",
        },
        "ip_broad_scope": {
            "mitigation": "建议明确约定知识产权的具体范围",
            "clause_template": "本合同涉及的知识产权仅限于本项目直接相关的技术成果，不包括各方的背景知识产权和通用技术。",
            "priority": "medium",
            "effort": "low",
        },

        # 保密风险
        "confidentiality_permanent": {
            "mitigation": "建议设定合理保密期限",
            "clause_template": "保密期限为本合同终止后【3】年。超过保密期限的信息不再受本条款约束。",
            "priority": "medium",
            "effort": "low",
        },
        "confidentiality_broad": {
            "mitigation": "建议明确界定保密信息的具体范围",
            "clause_template": "保密信息指一方披露的、标注为'保密'的、或根据信息性质和披露方式应被合理认为属于保密的所有信息。",
            "priority": "low",
            "effort": "low",
        },

        # 终止风险
        "termination_unilateral": {
            "mitigation": "建议双方解除权对等，或明确不对等的合理理由",
            "clause_template": "任何一方提前解除本合同的，应提前【30】日书面通知对方，并承担因解除给对方造成的直接损失。",
            "priority": "high",
            "effort": "medium",
        },
        "auto_renewal": {
            "mitigation": "建议设置自动续约的次数上限和提前通知期",
            "clause_template": "本合同到期后自动续约【1】年，除非任何一方在到期前【60】日书面通知不续约。自动续约最多不超过【2】次。",
            "priority": "medium",
            "effort": "low",
        },

        # 争议解决风险
        "dispute_no_mechanism": {
            "mitigation": "建议增加争议解决条款",
            "clause_template": "因本合同引起的或与本合同有关的任何争议，双方应首先通过友好协商解决。协商不成的，任何一方可向【甲方所在地】人民法院提起诉讼。",
            "priority": "high",
            "effort": "low",
        },
        "dispute_both": {
            "mitigation": "建议选择仲裁或诉讼中的一种",
            "clause_template": "因本合同引起的或与本合同有关的任何争议，提交【XX仲裁委员会】按其仲裁规则进行仲裁。仲裁裁决是终局的，对双方均有约束力。",
            "priority": "medium",
            "effort": "low",
        },

        # 不可抗力
        "no_force_majeure": {
            "mitigation": "建议增加不可抗力条款",
            "clause_template": "因不可抗力导致本合同无法履行的，受影响一方应在不可抗力发生后【7】日内书面通知对方，并提供相关证明。双方均不承担违约责任，但应协商解决后续事宜。",
            "priority": "medium",
            "effort": "low",
        },

        # 期限风险
        "deadline_tight": {
            "mitigation": "建议合理评估履约能力，设置里程碑节点",
            "clause_template": "乙方应按以下里程碑节点完成工作：第一阶段【XX】日前完成【XX】；第二阶段【XX】日前完成【XX】。如需延期，双方应协商调整。",
            "priority": "medium",
            "effort": "medium",
        },
    }

    # 默认缓解建议
    DEFAULT_MITIGATION = {
        "mitigation": "建议与专业法律顾问确认相关条款",
        "clause_template": "",
        "priority": "medium",
        "effort": "medium",
    }

    def __init__(self):
        super().__init__(
            skill_id="mitigation_suggester",
            name="风险缓解",
            description="为识别出的风险生成具体的缓解建议和条款修改模板",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行风险缓解建议生成

        Args:
            **kwargs:
                - risks: 风险列表（必填，来自RiskIdentifierSkill）
                - scored_risks: 量化后的风险列表（可选，来自RiskScorerSkill）

        Returns:
            缓解建议结果
        """
        risks = kwargs.get("risks", [])
        scored_risks = kwargs.get("scored_risks", [])

        if not risks and not scored_risks:
            return {"error": "请提供风险列表"}

        # 优先使用量化后的风险
        source = scored_risks if scored_risks else risks

        try:
            # 1. 生成缓解建议
            mitigations = self._generate_mitigations(source)

            # 2. 按优先级排序
            prioritized = self._prioritize(mitigations)

            # 3. 统计
            priority_count = {"high": 0, "medium": 0, "low": 0}
            for m in prioritized:
                p = m.get("priority", "medium")
                priority_count[p] = priority_count.get(p, 0) + 1

            return {
                "total_mitigations": len(prioritized),
                "mitigations": prioritized,
                "priority_distribution": priority_count,
                "summary": {
                    "high_priority": priority_count["high"],
                    "medium_priority": priority_count["medium"],
                    "low_priority": priority_count["low"],
                    "has_clause_templates": any(m.get("clause_template") for m in prioritized),
                },
            }
        except Exception as e:
            logger.error(f"风险缓解建议生成失败: {e}")
            return {"error": str(e)}

    def _generate_mitigations(self, risks: List[Dict]) -> List[Dict[str, Any]]:
        """为每个风险生成缓解建议"""
        mitigations = []
        seen_risk_ids = set()

        for risk in risks:
            risk_id = risk.get("risk_id", "")
            if risk_id in seen_risk_ids:
                continue
            seen_risk_ids.add(risk_id)

            template = self.MITIGATION_TEMPLATES.get(risk_id, self.DEFAULT_MITIGATION)

            # 如果有量化分数，调整优先级
            priority = template["priority"]
            score = risk.get("score", 0)
            if score >= 60:
                priority = "high"
            elif score >= 40:
                priority = max(priority, "medium") if priority != "high" else "high"

            mitigations.append({
                "risk_id": risk_id,
                "risk_name": risk.get("name", ""),
                "category": risk.get("category", ""),
                "severity": risk.get("severity", "medium"),
                "score": score,
                "mitigation": template["mitigation"],
                "clause_template": template["clause_template"],
                "priority": priority,
                "effort": template["effort"],
                "suggestion": risk.get("suggestion", ""),
            })

        return mitigations

    def _prioritize(self, mitigations: List[Dict]) -> List[Dict]:
        """按优先级和分数排序"""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            mitigations,
            key=lambda x: (priority_order.get(x["priority"], 2), -x.get("score", 0))
        )

    def get_mitigation_by_risk_id(self, risk_id: str) -> Dict[str, Any]:
        """按风险ID获取缓解建议"""
        return self.MITIGATION_TEMPLATES.get(risk_id, self.DEFAULT_MITIGATION)

    def get_all_templates(self) -> Dict[str, Dict]:
        """获取所有缓解模板"""
        return self.MITIGATION_TEMPLATES.copy()
