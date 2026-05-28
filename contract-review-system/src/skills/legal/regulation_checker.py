"""
法规检查Skill - 检查合同条款是否符合相关法律法规
"""
from typing import Any, Dict, List, Optional
import re
import logging

from ..base_skill import BaseSkill

logger = logging.getLogger(__name__)


class RegulationCheckerSkill(BaseSkill):
    """
    法规检查Skill

    功能：
    - 检查合同条款是否符合相关法律法规
    - 识别违规条款
    - 提供法规引用和修改建议
    """

    # 常见法规规则库
    REGULATION_RULES = [
        {
            "id": "civil_code_506",
            "name": "《民法典》第506条",
            "category": "免责条款",
            "pattern": r"免除.*一切.*责任|一切.*后果.*概不负责|对.*一切.*损失.*不承担责任",
            "severity": "high",
            "description": "免责条款不能免除造成对方人身损害或因故意/重大过失造成财产损失的责任",
            "suggestion": "建议删除'一切'等绝对化表述，明确免责范围",
        },
        {
            "id": "civil_code_585_penalty",
            "name": "《民法典》第585条",
            "category": "违约金",
            "pattern": r"违约金[^\d]*?(\d{3,})\s*%|违约金[^\d]*?(\d{4,})\s*元",
            "severity": "medium",
            "description": "违约金过高，一般不超过实际损失的30%",
            "suggestion": "建议将违约金调整为合理比例（不超过实际损失的30%）",
            "extract_group": [1, 2],
        },
        {
            "id": "arbitration_law_5",
            "name": "《仲裁法》第5条",
            "category": "争议解决",
            "pattern": r"仲裁.*诉讼|诉讼.*仲裁",
            "severity": "medium",
            "description": "仲裁和诉讼不能同时约定，当事人只能选择其一",
            "suggestion": "建议选择仲裁或诉讼中的一种作为争议解决方式",
        },
        {
            "id": "labor_law_working_hours",
            "name": "《劳动法》第36条",
            "category": "工作时间",
            "pattern": r"每日工作.*?(\d{2})小时以上|每周工作.*?(\d{2,3})小时以上",
            "severity": "high",
            "description": "劳动法规定每日工作不超过8小时，每周不超过44小时",
            "suggestion": "建议将工作时间调整为法定标准以内",
            "extract_group": [1, 2],
        },
        {
            "id": "labor_law_overtime",
            "name": "《劳动法》第44条",
            "category": "加班",
            "pattern": r"加班.*不支付|不支付.*加班|加班费.*免除",
            "severity": "high",
            "description": "用人单位不得免除支付加班费的义务",
            "suggestion": "建议删除加班费免除条款，依法支付加班费",
        },
        {
            "id": "consumer_protection",
            "name": "《消费者权益保护法》",
            "category": "格式条款",
            "pattern": r"一经售出.*概不退换|售出.*不退|不接受.*退换",
            "severity": "medium",
            "description": "格式条款中排除消费者退换货权利可能无效",
            "suggestion": "建议增加合理的退换货条款",
        },
        {
            "id": "data_protection",
            "name": "《个人信息保护法》",
            "category": "数据保护",
            "pattern": r"可将.*信息.*共享.*第三方|可向.*第三方.*提供.*个人信息",
            "severity": "medium",
            "description": "向第三方提供个人信息需取得个人同意",
            "suggestion": "建议明确个人信息共享的范围和同意机制",
        },
        {
            "id": "ip_ownership",
            "name": "《著作权法》/《专利法》",
            "category": "知识产权",
            "pattern": r"所有.*成果.*归.*甲方|一切.*知识产权.*归.*甲方",
            "severity": "low",
            "description": "职务作品和委托作品的知识产权归属需明确约定",
            "suggestion": "建议明确区分职务作品和委托作品，约定合理的知识产权归属",
        },
    ]

    def __init__(self):
        super().__init__(
            skill_id="regulation_checker",
            name="法规检查",
            description="检查合同条款是否符合相关法律法规，识别违规条款",
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行法规检查

        Args:
            **kwargs:
                - text: 合同文本（必填）
                - contract_type: 合同类型（可选）
                - regulations: 自定义法规规则（可选）

        Returns:
            法规检查结果
        """
        text = kwargs.get("text", "")
        contract_type = kwargs.get("contract_type", "general")
        custom_regulations = kwargs.get("regulations")

        if not text:
            return {"error": "请提供合同文本"}

        try:
            rules = custom_regulations or self.REGULATION_RULES

            # 1. 执行规则匹配
            violations = self._check_violations(text, rules)

            # 2. 检查必备条款
            missing = self._check_mandatory_clauses(text, contract_type)

            # 3. 统计结果
            total_rules = len(rules)
            violated_rules = len(set(v["rule_id"] for v in violations))

            return {
                "total_rules_checked": total_rules,
                "violations_found": len(violations),
                "violations": violations,
                "missing_clauses": missing,
                "compliance_score": max(
                    0, int(((total_rules - violated_rules) / total_rules) * 100)
                ),
                "summary": {
                    "high_severity": len([v for v in violations if v["severity"] == "high"]),
                    "medium_severity": len([v for v in violations if v["severity"] == "medium"]),
                    "low_severity": len([v for v in violations if v["severity"] == "low"]),
                },
            }
        except Exception as e:
            logger.error(f"法规检查失败: {e}")
            return {"error": str(e)}

    def _check_violations(
        self, text: str, rules: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        检查违规条款

        Args:
            text: 合同文本
            rules: 法规规则列表

        Returns:
            违规列表
        """
        violations = []

        for rule in rules:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue

            matches = re.finditer(pattern, text)
            for match in matches:
                # 提取匹配的上下文
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace("\n", " ")

                violations.append({
                    "rule_id": rule["id"],
                    "regulation": rule["name"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "suggestion": rule["suggestion"],
                    "matched_text": match.group(0),
                    "context": context,
                })

        return violations

    def _check_mandatory_clauses(
        self, text: str, contract_type: str
    ) -> List[Dict[str, Any]]:
        """
        检查必备条款

        Args:
            text: 合同文本
            contract_type: 合同类型

        Returns:
            缺失的必备条款列表
        """
        mandatory = {
            "sales": [
                ("标的物", ["标的物", "产品", "商品", "货物"]),
                ("价款", ["价款", "价格", "金额", "总价"]),
                ("交付", ["交付", "交货", "发货"]),
                ("验收", ["验收", "检验", "质量标准"]),
                ("违约责任", ["违约", "赔偿", "违约金"]),
                ("争议解决", ["争议", "纠纷", "仲裁", "诉讼"]),
            ],
            "labor": [
                ("工作内容", ["工作内容", "岗位", "职责"]),
                ("劳动报酬", ["工资", "薪酬", "报酬", "薪资"]),
                ("工作时间", ["工作时间", "工时", "上班"]),
                ("社会保险", ["社保", "社会保险", "五险"]),
                ("劳动保护", ["劳动保护", "安全", "防护"]),
                ("解除条件", ["解除", "终止", "离职", "辞退"]),
            ],
            "lease": [
                ("租赁物", ["租赁物", "房屋", "场地", "设备"]),
                ("租期", ["租期", "租赁期限", "承租期"]),
                ("租金", ["租金", "月租", "年租"]),
                ("维修责任", ["维修", "维护", "修缮"]),
                ("违约责任", ["违约", "赔偿", "违约金"]),
            ],
            "general": [
                ("合同标的", ["标的", "目的", "内容"]),
                ("价款报酬", ["价款", "报酬", "费用", "金额"]),
                ("履行期限", ["期限", "时间", "交付日期"]),
                ("违约责任", ["违约", "赔偿", "违约金"]),
                ("争议解决", ["争议", "纠纷", "仲裁", "诉讼"]),
            ],
        }

        clauses = mandatory.get(contract_type, mandatory["general"])
        missing = []

        for clause_name, keywords in clauses:
            found = any(kw in text for kw in keywords)
            if not found:
                missing.append({
                    "clause_name": clause_name,
                    "keywords": keywords,
                    "severity": "high" if clause_name in ["违约责任", "争议解决"] else "medium",
                    "suggestion": f"建议增加{clause_name}条款",
                })

        return missing
