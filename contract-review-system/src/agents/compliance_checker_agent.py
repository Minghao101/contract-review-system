"""
合规检查Agent模块 - LLM驱动，检查合同法规合规性
"""
from typing import Any, Dict, List, Optional
import re
import json
import logging

from src.utils.llm_response import parse_json_from_llm

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from src.memory.memory_layer import MemoryLayer

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

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）

        Args:
            task: 任务数据（兼容旧模式）

        Returns:
            合规检查结果
        """
        # 优先从共享内存读取（事件驱动模式）
        contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT) or ""
        contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT) or "general"

        # 兼容旧模式：从 task 参数读取
        if not contract_text:
            contract_text = task.get("contract_text", "")
        if contract_type == "general":
            contract_type = task.get("contract_type", "general")

        if not contract_text:
            return {"error": "合同文本为空"}

        # 更新状态
        self.set_running(True)
        self.update_activity()

        try:
            logger.info(f"开始合规检查，合同类型: {contract_type}，文本长度: {len(contract_text)}")

            result = await self._check_with_llm(contract_text, contract_type)

            if "error" in result:
                return result

            logger.info(f"合规检查完成，合规状态: {result.get('compliance_status', 'unknown')}")

            # 阶段1：写入共享内存 + 发布事件
            self.write_shared("compliance_result", result, MemoryLayer.ANALYSIS)
            self.publish_event(BusinessEvent.COMPLIANCE_CHECKED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.COMPLIANCE_CHECKED}")

            return result
        except Exception as e:
            logger.error(f"合规检查Agent异常: {e}", exc_info=True)
            error_result = {"error": str(e), "compliance_status": "unknown", "checked_regulations": [], "missing_clauses": [], "compliance_violations": [], "score": 0, "summary": {}}
            self.write_shared("compliance_result", error_result, MemoryLayer.ANALYSIS)
            self.publish_event(BusinessEvent.COMPLIANCE_CHECKED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)
            # 聚合屏障：递减计数器（归零时自动触发 ReportGenerator）
            self.decrement_pending_count()

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

        user_message = f"请检查以下合同的合规性：\n\n{text[:8000]}"

        try:
            content = await self.chat(user_message, system_prompt)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                return self._validate_result(result, contract_type)
        except Exception as e:
            logger.error(f"LLM合规检查失败: {e}")
            return {
                "compliance_status": "unknown",
                "checked_regulations": [],
                "missing_clauses": [],
                "compliance_violations": [],
                "score": 0,
                "summary": {"total_checked": 0, "error": str(e)},
            }

        return {
            "compliance_status": "unknown",
            "checked_regulations": [],
            "missing_clauses": [],
            "compliance_violations": [],
            "score": 0,
            "summary": {"total_checked": 0},
        }

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
        result.setdefault("compliance_status", "partial")
        result.setdefault("checked_regulations", [])
        result.setdefault("missing_clauses", [])
        result.setdefault("compliance_violations", [])
        result.setdefault("score", 0)
        result.setdefault("summary", {})
        return result

