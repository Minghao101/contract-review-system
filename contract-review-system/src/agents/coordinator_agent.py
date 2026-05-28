"""
协调器Agent模块 - 智能任务调度和流程控制
"""
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from .base_agent import BaseAgent
from .communication import MessageBus, AgentMessage, MessageType

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    协调器Agent（智能决策版）

    职责：
    - 理解用户意图
    - 智能决策需要调用哪些Agent
    - 动态生成执行计划
    - 根据中间结果决定下一步
    - 并行/串行混合执行
    """

    def __init__(
        self,
        agent_id: str = "coordinator",
        name: str = "协调器",
        message_bus: Optional[MessageBus] = None,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="coordinator",
            description="智能任务调度协调器",
            **kwargs
        )
        self.message_bus = message_bus or MessageBus()
        self._registered_agents: Dict[str, BaseAgent] = {}

        logger.info(f"协调器Agent初始化完成: {name}")

    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self._registered_agents[agent.agent_id] = agent
        logger.info(f"注册Agent: {agent.name} ({agent.agent_id})")

    def get_registered_agents(self) -> List[Dict[str, Any]]:
        """获取所有已注册Agent的状态"""
        return [agent.get_status() for agent in self._registered_agents.values()]

    def _get_agent_descriptions(self) -> str:
        """获取所有Agent的描述，用于LLM决策"""
        descriptions = []
        for agent in self._registered_agents.values():
            descriptions.append(f"- {agent.name} ({agent.role}): {agent.description}")
        return "\n".join(descriptions)

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务（智能决策版）

        Args:
            task: 任务数据

        Returns:
            处理结果
        """
        self.set_running(True)
        start_time = datetime.now()

        try:
            contract_text = task.get("contract_text", "")
            if not contract_text:
                return {"error": "合同文本不能为空"}

            logger.info(f"开始处理任务，文本长度: {len(contract_text)}")

            # 1. 智能决策：生成执行计划
            execution_plan = await self._plan_execution(task)
            logger.info(f"执行计划: {json.dumps([p['task_name'] for p in execution_plan], ensure_ascii=False)}")

            # 2. 执行计划
            results = await self._execute_plan(execution_plan, task, contract_text)

            # 3. 汇总结果
            final_result = self._aggregate_results(results, task)

            # 4. 发送完成消息
            self._publish_completion(final_result)

            elapsed = (datetime.now() - start_time).total_seconds()
            final_result["elapsed_seconds"] = elapsed
            final_result["execution_plan"] = [p["task_name"] for p in execution_plan]

            logger.info(f"任务完成，耗时: {elapsed:.2f}秒")
            return final_result

        except Exception as e:
            logger.error(f"处理任务失败: {e}")
            return {"error": str(e)}
        finally:
            self.set_running(False)

    async def _plan_execution(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        使用LLM规划执行计划

        Args:
            task: 原始任务

        Returns:
            执行计划列表
        """
        contract_text = task.get("contract_text", "")
        contract_type = task.get("contract_type", "general")
        review_focus = task.get("review_focus", [])

        system_prompt = """你是一个智能任务规划专家。根据用户需求和可用的Agent，制定最优执行计划。

可用的Agent：
{agent_descriptions}

规则：
1. 分析任务需求，决定需要哪些Agent
2. 确定执行顺序（有依赖关系的串行，无依赖的可并行）
3. 为每个步骤准备输入参数
4. 输出JSON格式的执行计划

输出格式（必须是有效的JSON数组）：
[
  {{
    "task_name": "任务名称",
    "agent_role": "agent角色",
    "input_keys": ["需要的输入键"],
    "depends_on": ["依赖的其他任务名称，没有则为空数组"],
    "parallel": false
  }}
]"""

        human_prompt = f"""任务信息：
- 合同类型: {contract_type}
- 审查重点: {review_focus if review_focus else '全面审查'}
- 合同文本前500字: {contract_text[:500]}...

请制定执行计划，只输出JSON数组，不要其他内容。"""

        messages = [
            SystemMessage(content=system_prompt.format(
                agent_descriptions=self._get_agent_descriptions()
            )),
            HumanMessage(content=human_prompt)
        ]

        try:
            response = self.llm.invoke(messages)
            content = response.content.strip()

            # 提取JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            plan = json.loads(content)
            if isinstance(plan, list) and len(plan) > 0:
                return plan
        except Exception as e:
            logger.warning(f"LLM规划失败，使用默认计划: {e}")

        # 默认执行计划
        return self._get_default_plan()

    def _get_default_plan(self) -> List[Dict[str, Any]]:
        """默认执行计划（LLM失败时的回退）"""
        return [
            {
                "task_name": "parse_document",
                "agent_role": "document_parser",
                "input_keys": ["contract_text", "contract_type"],
                "depends_on": [],
                "parallel": False
            },
            {
                "task_name": "analyze_clauses",
                "agent_role": "clause_analyst",
                "input_keys": ["contract_text", "review_focus"],
                "depends_on": [],
                "parallel": True
            },
            {
                "task_name": "assess_risks",
                "agent_role": "risk_assessor",
                "input_keys": ["contract_text", "contract_type"],
                "depends_on": [],
                "parallel": True
            },
            {
                "task_name": "compliance_check",
                "agent_role": "compliance_checker",
                "input_keys": ["contract_text", "contract_type"],
                "depends_on": [],
                "parallel": True
            },
            {
                "task_name": "generate_report",
                "agent_role": "report_generator",
                "input_keys": ["previous_results"],
                "depends_on": ["parse_document", "analyze_clauses", "assess_risks", "compliance_check"],
                "parallel": False
            },
        ]

    async def _execute_plan(
        self,
        plan: List[Dict[str, Any]],
        original_task: Dict[str, Any],
        contract_text: str
    ) -> Dict[str, Any]:
        """
        执行计划（支持并行）

        Args:
            plan: 执行计划
            original_task: 原始任务
            contract_text: 合同文本

        Returns:
            执行结果
        """
        import asyncio

        results = {}
        completed = set()

        # 构建任务图
        task_map = {p["task_name"]: p for p in plan}

        # 执行直到所有任务完成
        while len(completed) < len(plan):
            # 找出可以执行的任务（依赖已满足）
            ready_tasks = []
            for task_name, task_info in task_map.items():
                if task_name in completed:
                    continue
                deps = task_info.get("depends_on", [])
                if all(d in completed for d in deps):
                    ready_tasks.append(task_name)

            if not ready_tasks:
                logger.error("死锁：没有可执行的任务")
                break

            # 执行就绪的任务（可并行）
            tasks_to_run = []
            for task_name in ready_tasks:
                task_info = task_map[task_name]
                agent_role = task_info["agent_role"]

                agent = self._find_agent_by_role(agent_role)
                if agent is None:
                    logger.warning(f"未找到Agent: {agent_role}")
                    results[task_name] = {"status": "skipped", "reason": "no_agent"}
                    completed.add(task_name)
                    continue

                # 准备输入
                task_input = self._prepare_input(
                    task_info, original_task, contract_text, results
                )

                tasks_to_run.append((task_name, agent, task_input))

            # 并行执行
            if tasks_to_run:
                async_tasks = []
                for task_name, agent, task_input in tasks_to_run:
                    async_tasks.append(
                        self._execute_single(task_name, agent, task_input)
                    )

                # 并行等待所有任务完成
                task_results = await asyncio.gather(*async_tasks, return_exceptions=True)

                for (task_name, _, _), result in zip(tasks_to_run, task_results):
                    if isinstance(result, Exception):
                        results[task_name] = {"status": "failed", "error": str(result)}
                    else:
                        results[task_name] = result
                    completed.add(task_name)

        return results

    def _prepare_input(
        self,
        task_info: Dict[str, Any],
        original_task: Dict[str, Any],
        contract_text: str,
        previous_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """准备任务输入"""
        input_keys = task_info.get("input_keys", [])
        task_input = {}

        for key in input_keys:
            if key == "contract_text":
                task_input["contract_text"] = contract_text
            elif key == "contract_type":
                task_input["contract_type"] = original_task.get("contract_type", "general")
            elif key == "review_focus":
                task_input["review_focus"] = original_task.get("review_focus", [])
            elif key == "previous_results":
                task_input["previous_results"] = previous_results
            else:
                # 从原始任务中获取
                if key in original_task:
                    task_input[key] = original_task[key]

        return task_input

    async def _execute_single(
        self,
        task_name: str,
        agent: BaseAgent,
        task_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行单个任务"""
        try:
            self._publish_task_start(task_name, agent)
            result = await agent.process(task_input)
            self._publish_task_complete(task_name, result)
            return {"status": "completed", "result": result}
        except Exception as e:
            logger.error(f"执行任务失败 [{task_name}]: {e}")
            return {"status": "failed", "error": str(e)}

    def _find_agent_by_role(self, role: str) -> Optional[BaseAgent]:
        """根据角色查找Agent"""
        for agent in self._registered_agents.values():
            if agent.role == role:
                return agent
        return None

    def _aggregate_results(
        self,
        results: Dict[str, Any],
        original_task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """汇总结果"""
        aggregated = {
            "status": "completed",
            "contract_type": original_task.get("contract_type", "general"),
            "sections": {},
            "risk_level": "unknown",
            "recommendations": []
        }

        for task_name, task_result in results.items():
            if task_result.get("status") != "completed":
                continue

            result = task_result.get("result", {})

            if task_name == "parse_document":
                aggregated["document_info"] = result.get("document_info", {})
            elif task_name == "analyze_clauses":
                aggregated["sections"] = result.get("sections", {})
                aggregated["clause_analysis"] = result.get("analysis", {})
            elif task_name == "assess_risks":
                aggregated["risk_level"] = result.get("risk_level", "unknown")
                aggregated["risks"] = result.get("risks", [])
                aggregated["risk_quantification"] = result.get("risk_quantification", {})
                aggregated["mitigation_plan"] = result.get("mitigation_plan", [])
                aggregated["recommendations"] = result.get("recommendations", [])
            elif task_name == "compliance_check":
                aggregated["compliance_status"] = result.get("compliance_status", "unknown")
                aggregated["compliance_score"] = result.get("score", 0)
                aggregated["compliance_violations"] = result.get("compliance_violations", [])
                aggregated["missing_clauses"] = result.get("missing_clauses", [])
                aggregated["compliance_summary"] = result.get("summary", {})
            elif task_name == "generate_report":
                aggregated["report"] = result.get("report", {})
                aggregated["summary"] = result.get("summary", {})

        # 计算状态
        any_failed = any(r.get("status") == "failed" for r in results.values())
        if any_failed:
            aggregated["status"] = "partial_failed"

        return aggregated

    def _publish_task_start(self, task_name: str, agent: BaseAgent):
        """发布任务开始消息"""
        message = AgentMessage(
            sender_id=self.agent_id,
            receiver_id=agent.agent_id,
            message_type=MessageType.TASK_ASSIGN,
            content={"action": "start", "task_name": task_name}
        )
        self.message_bus.publish(message)

    def _publish_task_complete(self, task_name: str, result: Dict[str, Any]):
        """发布任务完成消息"""
        message = AgentMessage(
            sender_id=self.agent_id,
            receiver_id="all",
            message_type=MessageType.TASK_RESULT,
            content={
                "action": "complete",
                "task_name": task_name,
                "result_summary": list(result.keys()) if isinstance(result, dict) else []
            }
        )
        self.message_bus.publish(message)

    def _publish_completion(self, final_result: Dict[str, Any]):
        """发布完成消息"""
        message = AgentMessage(
            sender_id=self.agent_id,
            receiver_id="all",
            message_type=MessageType.TASK_RESULT,
            content={
                "action": "review_complete",
                "status": final_result.get("status"),
                "risk_level": final_result.get("risk_level")
            }
        )
        self.message_bus.publish(message)
