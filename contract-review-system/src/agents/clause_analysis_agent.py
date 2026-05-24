"""
条款分析Agent模块 - 负责分析合同条款
"""
from typing import Any, Dict, List, Optional
import re
import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ClauseAnalysisAgent(BaseAgent):
    """
    条款分析Agent

    职责：
    - 分析合同条款完整性
    - 识别关键条款
    - 检测模糊或不明确条款
    - 评估条款合理性
    """

    def __init__(
        self,
        agent_id: str = "clause_analyst",
        name: str = "条款分析Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="clause_analyst",
            description="负责分析合同条款的完整性和合理性",
            **kwargs
        )

        # 必备条款模板
        self._required_clauses = {
            "general": [
                "合同标的",
                "价款或报酬",
                "履行期限",
                "履行地点和方式",
                "违约责任",
                "争议解决",
            ],
            "sales": [
                "标的物",
                "数量和质量",
                "价款",
                "交付方式",
                "验收标准",
                "违约责任",
            ],
            "service": [
                "服务内容",
                "服务期限",
                "服务费用",
                "服务标准",
                "保密条款",
                "违约责任",
            ],
            "lease": [
                "租赁物",
                "租赁期限",
                "租金及支付方式",
                "租赁物使用",
                "维修责任",
                "违约责任",
            ],
            "labor": [
                "工作内容",
                "工作地点",
                "劳动报酬",
                "工作时间",
                "社会保险",
                "合同解除",
            ],
        }

        # 风险关键词
        self._risk_keywords = {
            "high": ["无限责任", "不可抗力排除", "单方面", "自动续约", "永久"],
            "medium": ["违约金过高", "管辖权约定", "知识产权归属不明确"],
            "low": ["付款期限超过90天", "交付时间不确定"],
        }

        logger.info(f"条款分析Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理条款分析任务

        Args:
            task: 任务数据
                - contract_text: 合同文本
                - review_focus: 审查重点 (可选)

        Returns:
            分析结果
        """
        contract_text = task.get("contract_text", "")
        review_focus = task.get("review_focus", [])

        if not contract_text:
            return {"error": "合同文本为空"}

        logger.info(f"开始分析合同条款，文本长度: {len(contract_text)}")

        # 1. 分析条款完整性
        completeness = self._analyze_completeness(contract_text)

        # 2. 识别模糊条款
        ambiguous_clauses = self._find_ambiguous_clauses(contract_text)

        # 3. 提取关键条款内容
        key_clauses = self._extract_key_clauses(contract_text)

        # 4. 分析权利义务
        rights_obligations = self._analyze_rights_obligations(contract_text)

        # 5. 生成分析摘要
        analysis_summary = self._generate_analysis_summary(
            completeness,
            ambiguous_clauses,
            key_clauses,
            rights_obligations
        )

        result = {
            "sections": key_clauses,
            "analysis": {
                "completeness": completeness,
                "ambiguous_clauses": ambiguous_clauses,
                "rights_obligations": rights_obligations,
                "summary": analysis_summary,
            },
            "missing_clauses": completeness.get("missing", []),
            "issues_found": len(ambiguous_clauses),
        }

        logger.info(f"条款分析完成，发现问题: {len(ambiguous_clauses)}个")
        return result

    def _analyze_completeness(self, text: str) -> Dict[str, Any]:
        """
        分析条款完整性

        Args:
            text: 合同文本

        Returns:
            完整性分析结果
        """
        # 确定合同类型
        contract_type = self._detect_contract_type(text)

        # 获取对应的必备条款
        required = self._required_clauses.get(
            contract_type,
            self._required_clauses["general"]
        )

        # 检查每个必备条款是否存在
        found = []
        missing = []

        clause_indicators = {
            "合同标的": ["标的", "合同内容", "服务内容", "货物"],
            "价款或报酬": ["价款", "报酬", "费用", "租金", "工资"],
            "履行期限": ["期限", "有效期", "交付时间", "完成时间"],
            "履行地点和方式": ["地点", "方式", "交付", "运输"],
            "违约责任": ["违约", "赔偿", "责任"],
            "争议解决": ["争议", "仲裁", "诉讼", "管辖"],
            "标的物": ["标的物", "货物", "产品"],
            "数量和质量": ["数量", "质量", "规格", "标准"],
            "交付方式": ["交付", "发货", "运输"],
            "验收标准": ["验收", "检验", "测试"],
            "服务内容": ["服务内容", "服务范围", "工作内容"],
            "服务期限": ["服务期限", "合同期限", "有效期"],
            "服务费用": ["服务费", "费用", "报酬"],
            "服务标准": ["服务标准", "服务质量", "SLA"],
            "保密条款": ["保密", "机密", "不披露"],
            "租赁物": ["租赁物", "房屋", "设备"],
            "租赁期限": ["租赁期限", "租期"],
            "租金及支付方式": ["租金", "支付方式", "付款"],
            "租赁物使用": ["使用", "用途", "使用限制"],
            "维修责任": ["维修", "维护", "保养"],
            "工作内容": ["工作内容", "岗位职责", "工作任务"],
            "工作地点": ["工作地点", "工作场所"],
            "劳动报酬": ["工资", "薪酬", "报酬", "奖金"],
            "工作时间": ["工作时间", "工时", "考勤"],
            "社会保险": ["社保", "社会保险", "公积金"],
            "合同解除": ["解除", "终止", "解约"],
        }

        for clause_name in required:
            indicators = clause_indicators.get(clause_name, [clause_name])
            if any(indicator in text for indicator in indicators):
                found.append(clause_name)
            else:
                missing.append(clause_name)

        return {
            "contract_type": contract_type,
            "required": required,
            "found": found,
            "missing": missing,
            "completeness_score": len(found) / len(required) if required else 0,
        }

    def _detect_contract_type(self, text: str) -> str:
        """检测合同类型"""
        type_keywords = {
            "sales": ["销售", "买卖", "购销", "供货"],
            "service": ["服务", "委托", "咨询"],
            "lease": ["租赁", "出租", "承租"],
            "labor": ["劳动合同", "雇佣", "聘用"],
        }

        for contract_type, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                return contract_type

        return "general"

    def _find_ambiguous_clauses(self, text: str) -> List[Dict[str, Any]]:
        """
        查找模糊条款

        Args:
            text: 合同文本

        Returns:
            模糊条款列表
        """
        ambiguous = []

        # 模糊表述模式
        ambiguous_patterns = [
            (r"合理[的地]?时间", "时间表述模糊"),
            (r"适当[的地]?方式", "方式表述模糊"),
            (r"必要[的地]?措施", "措施表述模糊"),
            (r"相关[的]?费用", "费用表述模糊"),
            (r"其他[^。]*", "兜底条款可能过于宽泛"),
            (r"包括但不限于[^。]*", "范围可能过大"),
            (r"视情况[^。]*", "条件不明确"),
            (r"双方协商[^。]*", "缺乏明确标准"),
        ]

        for pattern, issue_type in ambiguous_patterns:
            for match in re.finditer(pattern, text):
                # 获取匹配内容的上下文
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace("\n", " ")

                ambiguous.append({
                    "issue_type": issue_type,
                    "content": match.group(0),
                    "context": f"...{context}...",
                    "position": match.start(),
                })

        return ambiguous

    def _extract_key_clauses(self, text: str) -> Dict[str, str]:
        """
        提取关键条款内容

        Args:
            text: 合同文本

        Returns:
            关键条款字典
        """
        key_clauses = {}

        # 条款标题模式
        clause_patterns = [
            r"第[一二三四五六七八九十百千]+条\s+(.+?)[\n：:]",
            r"[0-9]+[、.]\s*(.+?)[\n：:]",
        ]

        for pattern in clause_patterns:
            for match in re.finditer(pattern, text):
                clause_title = match.group(1).strip()

                # 提取条款内容（到下一个条款或文本结束）
                start_pos = match.end()
                next_clause_match = re.search(
                    r"第[一二三四五六七八九十百千]+条|[0-9]+[、.]",
                    text[start_pos:start_pos + 1000]
                )

                if next_clause_match:
                    end_pos = start_pos + next_clause_match.start()
                else:
                    end_pos = min(start_pos + 1000, len(text))

                clause_content = text[start_pos:end_pos].strip()

                if clause_title and len(clause_title) < 100:
                    key_clauses[clause_title] = clause_content[:500]

        return key_clauses

    def _analyze_rights_obligations(self, text: str) -> Dict[str, Any]:
        """
        分析权利义务关系

        Args:
            text: 合同文本

        Returns:
            权利义务分析结果
        """
        rights_keywords = ["有权", "权利", "享有", "可以", "有权要求"]
        obligations_keywords = ["应当", "必须", "有义务", "负责", "承担"]

        rights_count = sum(text.count(kw) for kw in rights_keywords)
        obligations_count = sum(text.count(kw) for kw in obligations_keywords)

        # 判断权利义务是否平衡
        balance_ratio = rights_count / obligations_count if obligations_count > 0 else 1

        if 0.7 <= balance_ratio <= 1.3:
            balance = "平衡"
        elif balance_ratio < 0.7:
            balance = "义务偏重"
        else:
            balance = "权利偏重"

        return {
            "rights_count": rights_count,
            "obligations_count": obligations_count,
            "balance_ratio": round(balance_ratio, 2),
            "balance_assessment": balance,
        }

    def _generate_analysis_summary(
        self,
        completeness: Dict[str, Any],
        ambiguous_clauses: List[Dict[str, Any]],
        key_clauses: Dict[str, str],
        rights_obligations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成分析摘要

        Args:
            completeness: 完整性分析结果
            ambiguous_clauses: 模糊条款列表
            key_clauses: 关键条款字典
            rights_obligations: 权利义务分析结果

        Returns:
            分析摘要
        """
        issues = []

        # 完整性问题
        if completeness["missing"]:
            issues.append({
                "type": "missing_clause",
                "severity": "high",
                "message": f"缺少必备条款: {', '.join(completeness['missing'])}"
            })

        # 模糊条款问题
        for clause in ambiguous_clauses:
            issues.append({
                "type": "ambiguous_clause",
                "severity": "medium",
                "message": f"{clause['issue_type']}: {clause['content']}"
            })

        # 权利义务不平衡
        if rights_obligations["balance_assessment"] != "平衡":
            issues.append({
                "type": "imbalance",
                "severity": "medium",
                "message": f"权利义务{rights_obligations['balance_assessment']}"
            })

        return {
            "total_clauses_found": len(key_clauses),
            "completeness_score": completeness["completeness_score"],
            "total_issues": len(issues),
            "issues": issues,
        }
