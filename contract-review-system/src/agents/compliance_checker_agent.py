"""
合规检查Agent模块 - LLM驱动，检查合同法规合规性
"""
from typing import Any, Dict, List, Optional
import re
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.llm_response import extract_llm_content, parse_json_from_llm

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


class ComplianceCheckerAgent(BaseAgent):
    """
    合规检查Agent（LLM驱动版）

    检查合同是否符合相关法律法规要求
    """

    # 各类合同的必备条款
    REQUIRED_CLAUSES = {
        "sales": ["标的物", "价款", "交付", "验收", "违约责任", "争议解决"],
        "service": ["服务内容", "服务期限", "服务费用", "验收标准", "违约责任", "保密"],
        "lease": ["租赁物", "租期", "租金", "维修责任", "违约责任", "终止条件"],
        "labor": ["工作内容", "劳动报酬", "工作时间", "社会保险", "劳动保护", "解除条件"],
        "nda": ["保密信息定义", "保密义务", "保密期限", "违约责任", "争议解决"],
        "partnership": ["出资方式", "利润分配", "亏损分担", "退出机制", "决策机制"],
        "general": ["合同标的", "价款报酬", "履行期限", "违约责任", "争议解决"],
    }

    def __init__(
        self,
        agent_id: str = "compliance_checker",
        name: str = "合规检查Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="compliance_checker",
            description="负责检查合同是否符合相关法律法规要求",
            **kwargs
        )
        logger.info(f"合规检查Agent初始化完成: {name}")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理合规检查任务

        Args:
            task: 任务数据
                - contract_text: 合同文本
                - contract_type: 合同类型 (可选)

        Returns:
            合规检查结果
        """
        contract_text = task.get("contract_text", "")
        contract_type = task.get("contract_type", "general")

        if not contract_text:
            return {"error": "合同文本为空"}

        logger.info(f"开始合规检查，合同类型: {contract_type}，文本长度: {len(contract_text)}")

        result = await self._check_with_llm(contract_text, contract_type)

        if "error" in result:
            return result

        logger.info(f"合规检查完成，合规状态: {result.get('compliance_status', 'unknown')}")
        return result

    async def _check_with_llm(self, text: str, contract_type: str) -> Dict[str, Any]:
        """
        使用LLM进行合规检查

        Args:
            text: 合同文本
            contract_type: 合同类型

        Returns:
            合规检查结果
        """
        required = self.REQUIRED_CLAUSES.get(contract_type, self.REQUIRED_CLAUSES["general"])

        system_prompt = f"""你是一个专业的合同合规审查专家。请检查合同是否符合相关法律法规要求。

当前合同类型: {contract_type}
该类型合同必备条款: {', '.join(required)}

输出格式要求（必须是严格有效的JSON）：
{{
  "compliance_status": "compliant/partial/non_compliant",
  "checked_regulations": [
    {{
      "regulation": "法规/标准名称",
      "status": "compliant/violation/missing",
      "details": "具体说明"
    }}
  ],
  "missing_clauses": ["缺失的必备条款"],
  "compliance_violations": [
    {{
      "clause": "有问题的条款内容",
      "regulation": "违反的法规或标准",
      "severity": "high/medium/low",
      "suggestion": "修改建议"
    }}
  ],
  "score": 85,
  "summary": {{
    "total_checked": 10,
    "compliant_count": 8,
    "violation_count": 1,
    "missing_count": 1,
    "assessment": "整体合规评估说明"
  }}
}}

检查要点：
1. 必备条款是否齐全（基于合同类型）
2. 是否符合《民法典》合同编相关规定
3. 是否符合行业特殊监管要求（如劳动、数据保护等）
4. 条款内容是否合法有效
5. 免责条款是否合理
6. 争议解决条款是否有效
7. 只输出JSON，不要其他内容"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请检查以下合同的合规性：\n\n{text[:8000]}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = extract_llm_content(response.content)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                return self._validate_result(result, contract_type)
        except Exception as e:
            logger.error(f"LLM合规检查失败: {e}")

        # 回退到规则检查
        return self._check_with_rules(text, contract_type)

    def _parse_json(self, content: str) -> Any:
        """容错JSON解析"""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        if HAS_JSON_REPAIR:
            try:
                return json_repair.loads(content)
            except Exception:
                pass

        try:
            fixed = re.sub(r',\s*([}\]])', r'\1', content)
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None

    def _validate_result(self, result: Dict[str, Any], contract_type: str) -> Dict[str, Any]:
        """验证并标准化LLM结果"""
        # 确保必要字段存在
        result.setdefault("compliance_status", "partial")
        result.setdefault("checked_regulations", [])
        result.setdefault("missing_clauses", [])
        result.setdefault("compliance_violations", [])
        result.setdefault("score", 0)
        result.setdefault("summary", {})

        # 自动检查必备条款缺失
        required = self.REQUIRED_CLAUSES.get(contract_type, self.REQUIRED_CLAUSES["general"])
        text_lower = json.dumps(result, ensure_ascii=False).lower()

        auto_missing = []
        for clause in required:
            if clause.lower() not in text_lower:
                # 检查是否在 missing_clauses 中已提及
                already_noted = any(
                    clause.lower() in m.lower()
                    for m in result.get("missing_clauses", [])
                )
                if not already_noted:
                    auto_missing.append(clause)

        result["missing_clauses"].extend(auto_missing)

        # 根据违规和缺失情况自动计算分数
        total_checked = len(required) + len(result.get("checked_regulations", []))
        violations = len(result.get("compliance_violations", []))
        missing = len(result.get("missing_clauses", []))

        if total_checked > 0:
            auto_score = max(0, int(((total_checked - violations - missing) / total_checked) * 100))
            # 取LLM分数和自动分数的较低值
            result["score"] = min(result.get("score", auto_score), auto_score)

        # 更新合规状态
        if violations > 2 or missing > 2:
            result["compliance_status"] = "non_compliant"
        elif violations > 0 or missing > 0:
            result["compliance_status"] = "partial"
        else:
            result["compliance_status"] = "compliant"

        return result

    def _check_with_rules(self, text: str, contract_type: str) -> Dict[str, Any]:
        """基于规则的合规检查（LLM失败回退）"""
        required = self.REQUIRED_CLAUSES.get(contract_type, self.REQUIRED_CLAUSES["general"])

        # 检查必备条款
        missing_clauses = []
        for clause in required:
            # 使用关键词匹配
            keywords = clause.split("/")
            found = any(kw in text for kw in keywords)
            if not found:
                missing_clauses.append(clause)

        # 检查常见合规问题
        violations = []

        # 检查免责条款
        if re.search(r"免除.*一切.*责任|一切.*后果.*概不负责", text):
            violations.append({
                "clause": "免责条款",
                "regulation": "《民法典》第506条",
                "severity": "high",
                "suggestion": "免责条款不能免除造成对方人身损害或因故意/重大过失造成财产损失的责任",
            })

        # 检查违约金
        match = re.search(r"违约金.*?(\d+)%", text)
        if match:
            rate = int(match.group(1))
            if rate > 30:
                violations.append({
                    "clause": f"违约金比例{rate}%",
                    "regulation": "《民法典》第585条",
                    "severity": "medium",
                    "suggestion": "违约金过高，建议不超过实际损失的30%",
                })

        # 检查管辖权
        if "仲裁" in text and "法院" in text:
            violations.append({
                "clause": "同时约定仲裁和诉讼",
                "regulation": "《仲裁法》第5条",
                "severity": "medium",
                "suggestion": "仲裁和诉讼不能同时约定，建议选择其一",
            })

        total_checked = len(required) + 3
        compliant_count = total_checked - len(missing_clauses) - len(violations)
        score = max(0, int((compliant_count / total_checked) * 100))

        compliance_status = "compliant"
        if violations:
            compliance_status = "non_compliant" if len(violations) > 2 else "partial"
        elif missing_clauses:
            compliance_status = "partial"

        return {
            "compliance_status": compliance_status,
            "checked_regulations": [],
            "missing_clauses": missing_clauses,
            "compliance_violations": violations,
            "score": score,
            "summary": {
                "total_checked": total_checked,
                "compliant_count": compliant_count,
                "violation_count": len(violations),
                "missing_count": len(missing_clauses),
                "assessment": f"基于规则检查，缺失{len(missing_clauses)}个必备条款，发现{len(violations)}个违规问题",
            },
        }
