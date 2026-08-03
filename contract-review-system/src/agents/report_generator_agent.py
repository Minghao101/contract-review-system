"""
报告生成Agent模块 - 使用 LangChain 高级抽象（ChatPromptTemplate + structured output）
"""
from typing import Any, Dict, Set
from datetime import datetime
import asyncio
import logging

from langchain_core.prompts import ChatPromptTemplate

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .schemas import ReportResult
from src.memory.memory_layer import MemoryLayer

logger = logging.getLogger(__name__)


class ReportGeneratorAgent(BaseAgent):
    """
    报告生成Agent（LangChain 高级抽象版）

    使用 ChatPromptTemplate 构建 prompt，with_structured_output 解析结果
    """

    # 输出模型
    output_model = ReportResult

    # ==================== Prompt 模板 ====================

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的合同审查报告撰写专家。请根据以下分析结果生成一份完整的合同审查报告。

报告要专业、清晰、易于理解。执行摘要要简洁明了，风险要按严重程度分类，建议要具体可执行，结论要明确。"""),
        ("human", """分析结果上下文：

文档解析结果: {document_info}

条款分析结果: {clause_analysis}

风险评估结果: {risk_assessment}

合规检查结果: {compliance_result}

请根据以上分析结果生成完整的审查报告。"""),
    ])

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

        # 事件驱动：订阅 3 个分析事件（聚合屏障）
        self._subscribed_events = [
            BusinessEvent.RISK_ANALYZED,
            BusinessEvent.CLAUSE_ANALYZED,
            BusinessEvent.COMPLIANCE_CHECKED,
        ]
        self._agent_to_event = {
            "risk_assessor": BusinessEvent.RISK_ANALYZED,
            "clause_analyst": BusinessEvent.CLAUSE_ANALYZED,
            "compliance_checker": BusinessEvent.COMPLIANCE_CHECKED,
        }
        self._received_events: Set[str] = set()
        self._aggregation_lock = asyncio.Lock()

        logger.info(f"报告生成Agent初始化完成: {name}")

    async def _handle_event(self, event_type: str, data: Dict[str, Any]):
        """
        聚合屏障：收到所有分析事件后才触发 process()
        """
        async with self._aggregation_lock:
            required_agents = self.read_shared("_required_agents", MemoryLayer.CONTEXT) or []
            required_events = set()
            for agent_id in required_agents:
                if agent_id in self._agent_to_event:
                    required_events.add(self._agent_to_event[agent_id])

            if not required_events:
                required_events = {
                    BusinessEvent.RISK_ANALYZED,
                    BusinessEvent.CLAUSE_ANALYZED,
                    BusinessEvent.COMPLIANCE_CHECKED,
                }

            self._received_events.add(event_type)
            logger.info(
                f"[{self.agent_id}] 聚合屏障: 收到 {event_type}, "
                f"已收到 {len(self._received_events)}/{len(required_events)}, "
                f"需要等待: {list(required_events)}"
            )

            if self._received_events >= required_events:
                self._received_events.clear()
                logger.info(f"[{self.agent_id}] 聚合屏障归零：所有分析完成，触发报告生成")
                task = {"session_id": data.get("session_id")}
                await self.process(task)
            else:
                logger.info(f"[{self.agent_id}] 聚合屏障: 等待剩余事件")

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理报告生成任务

        数据来源（优先级）：
        1. 共享内存（事件驱动模式）
        2. task 参数（兼容旧模式）
        """
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

        if not previous_results:
            previous_results = task.get("previous_results", {})

        self.set_running(True)
        self.update_activity()

        try:
            logger.info("开始生成审查报告")

            result = await self._generate_with_llm(previous_results)

            if "error" in result:
                return result

            logger.info("审查报告生成完成")

            # 写入共享内存 DECISION 层 + 发布事件
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
        使用 LangChain structured output 生成报告
        """
        import json

        document_info = previous_results.get("document_parser", {}).get("result", {})
        clause_analysis = previous_results.get("clause_analyst", {}).get("result", {})
        risk_assessment = previous_results.get("risk_assessor", {}).get("result", {})
        compliance_result = previous_results.get("compliance_checker", {}).get("result", {})

        try:
            result = await self.chat_structured(
                document_info=json.dumps(document_info, ensure_ascii=False, default=str)[:2000],
                clause_analysis=json.dumps(clause_analysis, ensure_ascii=False, default=str)[:2000],
                risk_assessment=json.dumps(risk_assessment, ensure_ascii=False, default=str)[:2000],
                compliance_result=json.dumps(compliance_result, ensure_ascii=False, default=str)[:2000],
            )
            result_dict = self._schema_to_dict(result)
            result_dict["generated_at"] = datetime.now().isoformat()
            return result_dict
        except Exception as e:
            logger.error(f"LLM报告生成失败: {e}")

        return self._generate_basic_report({
            "document_info": document_info,
            "clause_analysis": clause_analysis,
            "risk_assessment": risk_assessment,
        })

    def _schema_to_dict(self, result: ReportResult) -> Dict[str, Any]:
        """将 Pydantic 模型转换为兼容旧格式的字典"""
        return {
            "report": result.report.model_dump(),
            "summary": result.summary.model_dump(),
            "visualization": result.visualization.model_dump(),
        }

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
