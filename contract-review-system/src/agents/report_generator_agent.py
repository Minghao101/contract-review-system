"""
报告生成Agent模块 - LLM驱动，生成审查报告
"""
from typing import Any, Dict
from datetime import datetime
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


class ReportGeneratorAgent(BaseAgent):
    """
    报告生成Agent（LLM驱动版）

    使用LLM生成专业的审查报告
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

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）

        Args:
            task: 任务数据（兼容旧模式）

        Returns:
            报告生成结果
        """
        # 优先从共享内存读取所有分析结果（事件驱动模式）
        previous_results = {}
        parsed = self.read_shared("document_parser", MemoryLayer.ANALYSIS)
        risk = self.read_shared("risk_assessor", MemoryLayer.ANALYSIS)
        clause = self.read_shared("clause_analyst", MemoryLayer.ANALYSIS)
        compliance = self.read_shared("compliance_checker", MemoryLayer.ANALYSIS)

        if parsed:
            previous_results["document_parser"] = {"result": parsed}
        if risk:
            previous_results["risk_assessor"] = {"result": risk}
        if clause:
            previous_results["clause_analyst"] = {"result": clause}
        if compliance:
            previous_results["compliance_checker"] = {"result": compliance}

        # 兼容旧模式：从 task 参数读取
        if not previous_results:
            previous_results = task.get("previous_results", {})

        # 更新状态
        self.set_running(True)
        self.update_activity()

        try:
            logger.info("开始生成审查报告")

            # LLM生成报告
            result = await self._generate_with_llm(previous_results)

            if "error" in result:
                return result

            logger.info("审查报告生成完成")

            # 阶段1：写入共享内存 DECISION 层 + 发布事件
            self.write_shared("report_generator", result, MemoryLayer.DECISION, validate=False)
            risk_level = result.get("summary", {}).get("risk_level")
            if risk_level:
                self.write_shared("risk_level", risk_level, MemoryLayer.DECISION)
            self.publish_event(BusinessEvent.TASK_COMPLETED, {"session_id": task.get("session_id")})
            logger.info(f"已发布事件: {BusinessEvent.TASK_COMPLETED}")

            return result
        except Exception as e:
            logger.error(f"报告生成Agent异常: {e}", exc_info=True)
            error_result = {"error": str(e), "report": {}, "summary": {"risk_level": "unknown"}, "generated_at": datetime.now().isoformat()}
            self.write_shared("report_generator", error_result, MemoryLayer.DECISION, validate=False)
            self.publish_event(BusinessEvent.TASK_COMPLETED, {"session_id": task.get("session_id")})
            return error_result
        finally:
            self.set_running(False)

    async def _generate_with_llm(self, previous_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM生成报告

        Args:
            previous_results: 前面阶段的结果

        Returns:
            报告结果
        """
        # 提取各阶段结果（key 与 Agent 写入的 agent_id 一致）
        document_info = previous_results.get("document_parser", {}).get("result", {})
        clause_analysis = previous_results.get("clause_analyst", {}).get("result", {})
        risk_assessment = previous_results.get("risk_assessor", {}).get("result", {})

        # 准备上下文
        context = {
            "document_info": document_info,
            "clause_analysis": clause_analysis,
            "risk_assessment": risk_assessment,
        }

        system_prompt = """你是一个专业的合同审查报告撰写专家。请根据以下分析结果生成一份完整的合同审查报告。

输出格式要求（必须是严格有效的JSON）：
{
  "report": {
    "title": "合同审查报告",
    "executive_summary": "执行摘要（200字以内）",
    "document_overview": {
      "contract_type": "合同类型",
      "parties": ["甲方", "乙方"],
      "key_terms": "核心条款概述"
    },
    "completeness_analysis": {
      "score": 0.8,
      "found": ["已找到的条款"],
      "missing": ["缺失的条款"],
      "assessment": "完整性评估"
    },
    "risk_assessment": {
      "overall_level": "风险等级",
      "high_risks": ["高风险项"],
      "medium_risks": ["中风险项"],
      "low_risks": ["低风险项"]
    },
    "recommendations": [
      {
        "priority": "high/medium/low",
        "category": "类别",
        "content": "具体建议"
      }
    ],
    "conclusion": {
      "verdict": "建议签署/建议修改后签署/不建议签署",
      "reason": "结论原因",
      "next_steps": ["后续步骤"]
    }
  },
  "summary": {
    "risk_level": "风险等级",
    "completeness_score": 0.8,
    "total_issues": 5,
    "verdict": "最终结论"
  },
  "visualization": {
    "risk_distribution": {"high": 2, "medium": 3, "low": 1},
    "completeness_bar": 80
  }
}

规则：
1. 报告要专业、清晰、易于理解
2. 执行摘要要简洁明了
3. 风险要按严重程度分类
4. 建议要具体可执行
5. 结论要明确
6. 只输出JSON，不要其他内容"""

        user_message = f"""分析结果上下文：
{json.dumps(context, ensure_ascii=False, default=str)[:6000]}

请根据以上分析结果生成完整的审查报告，只输出JSON。"""

        try:
            content = await self.chat(user_message, system_prompt)

            result = parse_json_from_llm(content)

            if isinstance(result, dict):
                result["generated_at"] = datetime.now().isoformat()
                return result
        except Exception as e:
            logger.error(f"LLM报告生成失败: {e}")

        # 回退到基础报告
        return self._generate_basic_report(context)

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

    def _generate_basic_report(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成基础报告（回退）"""
        risk_assessment = context.get("risk_assessment", {})
        risk_level = risk_assessment.get("risk_level", "unknown")

        verdict_map = {
            "low": "建议签署",
            "medium": "建议修改后签署",
            "high": "建议大幅修改",
            "critical": "不建议签署",
        }

        return {
            "report": {
                "title": "合同审查报告",
                "executive_summary": "本报告基于自动化分析生成。",
                "conclusion": {
                    "verdict": verdict_map.get(risk_level, "需要人工审查"),
                    "reason": f"整体风险等级: {risk_level}",
                }
            },
            "summary": {
                "risk_level": risk_level,
                "verdict": verdict_map.get(risk_level, "需要人工审查"),
            },
            "generated_at": datetime.now().isoformat(),
        }
