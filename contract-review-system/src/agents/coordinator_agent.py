"""
协调器Agent模块 - 处理问候、未知意图、协调多Agent协作
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    协调器Agent

    职责：
    - 处理问候和未知意图
    - 注册和管理子Agent
    - 协调多Agent完成合同审查
    """

    def __init__(
        self,
        agent_id: str = "coordinator",
        name: str = "协调器",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="coordinator",
            description="处理问候、未知意图、协调多Agent协作",
            **kwargs
        )
        self._registered_agents: Dict[str, BaseAgent] = {}
        logger.info(f"协调器Agent初始化完成: {name}")

    def register_agent(self, agent: BaseAgent):
        """注册子Agent"""
        self._registered_agents[agent.agent_id] = agent
        logger.info(f"已注册Agent: {agent.name} ({agent.agent_id})")

    def get_registered_agents(self) -> List[BaseAgent]:
        """获取所有已注册的Agent"""
        return list(self._registered_agents.values())

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务

        Args:
            task: 任务数据

        Returns:
            处理结果
        """
        self.set_running(True)
        self.update_activity()

        try:
            intent = task.get("intent", {})
            intent_type = intent.get("type", "unknown")
            user_message = task.get("user_message", "")

            # 问候
            if intent_type == "greeting":
                return {
                    "status": "completed",
                    "message": "您好！我是智能合同审查助手，可以帮您：\n"
                              "- 审查合同\n"
                              "- 分析条款\n"
                              "- 评估风险\n"
                              "- 检查合规性\n"
                              "- 生成报告\n\n"
                              "请上传或粘贴合同文本，告诉我您需要什么帮助。"
                }

            # 合同审查任务：协调已注册的Agent并行执行
            contract_text = task.get("contract_text")
            if contract_text and self._registered_agents:
                return await self._execute_contract_review(task)

            # 未知意图
            if intent_type == "unknown":
                return {
                    "status": "completed",
                    "message": f"抱歉，我不太理解您的意思。您可以：\n"
                              "- 上传合同文本进行审查\n"
                              "- 告诉我具体需求（如：评估风险、分析条款）\n"
                              "- 问我关于合同的问题"
                }

            # 默认响应
            return {
                "status": "completed",
                "message": "您好！请问有什么可以帮助您的？"
            }

        finally:
            self.set_running(False)

    async def _execute_contract_review(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """协调多Agent并行执行合同审查"""
        contract_text = task["contract_text"]
        contract_type = task.get("contract_type", "general")
        review_focus = task.get("review_focus", [])

        # 先用 DocumentParser 解析合同
        doc_parser = self._registered_agents.get("document_parser")
        parse_result = None
        if doc_parser:
            parse_result = await doc_parser.process({
                "contract_text": contract_text,
                "contract_type": contract_type,
            })

        # 并行执行风险评估、条款分析、合规检查
        risk_level = "unknown"
        tasks_to_run = []
        agent_names = []

        for agent_id, agent in self._registered_agents.items():
            if agent_id == "document_parser" or agent_id == "report_generator":
                continue
            if agent_id == "risk_assessor":
                tasks_to_run.append(agent.process({
                    "contract_text": contract_text,
                    "contract_type": contract_type,
                }))
                agent_names.append(agent_id)
            elif agent_id == "clause_analyst":
                tasks_to_run.append(agent.process({
                    "contract_text": contract_text,
                    "review_focus": review_focus,
                }))
                agent_names.append(agent_id)
            elif agent_id == "compliance_checker":
                tasks_to_run.append(agent.process({
                    "contract_text": contract_text,
                    "contract_type": contract_type,
                }))
                agent_names.append(agent_id)

        # 并行执行
        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)

        # 收集风险等级
        for i, result in enumerate(results):
            if isinstance(result, dict) and "risk_level" in result:
                risk_level = result["risk_level"]
                break

        return {
            "status": "completed",
            "risk_level": risk_level,
            "parse_result": parse_result,
            "analysis_results": {
                name: result for name, result in zip(agent_names, results)
                if not isinstance(result, Exception)
            },
        }
