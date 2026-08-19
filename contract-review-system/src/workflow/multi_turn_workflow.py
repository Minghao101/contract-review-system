"""
多轮对话工作流 - 基于 LangGraph 的状态图实现

功能：
1. 对话历史管理
2. 意图识别和路由
3. Agent调度和结果收集
4. Checkpoint状态持久化

工作流拓扑（闭环循环）:
  START → process_user_input → recognize_intent → route_by_intent
                                                    ↓
                              ┌─────────────────────┼─────────────────────┐
                              ↓                     ↓                     ↓
                    execute_analysis_agents   handle_follow_up   handle_topic_discussion
                              ↓                     ↓                     ↓
                              └─────────────────────┼─────────────────────┘
                                                    ↓
                                            generate_response
                                                    ↓
                                            [human_review] (可选)
                                                    ↓
                                          wait_for_user_input
                                                    ↓
                                          【interrupt 暂停】
                                                    ↓
                                          恢复后 → should_continue_loop
                                              ↙              ↘
                                        END              process_user_input（下一轮）
"""
import operator
import asyncio
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from enum import Enum

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from src.agents.intent_recognizer import IntentRecognizer, IntentType, Intent
from src.agents.document_parser_agent import DocumentParserAgent
from src.agents.clause_analysis_agent import ClauseAnalysisAgent
from src.agents.risk_assessment_agent import RiskAssessmentAgent
from src.agents.compliance_checker_agent import ComplianceCheckerAgent
from src.agents.report_generator_agent import ReportGeneratorAgent
from src.memory.topic_board import TopicBoard, TopicResponse
from src.utils.llm_factory import get_llm

import logging

logger = logging.getLogger(__name__)

# ============================================================
# 状态定义
# ============================================================

class ConversationStatus(str, Enum):
    """对话状态"""
    IDLE = "idle"
    COLLECTING = "collecting"
    PROCESSING = "processing"
    WAITING_CONFIRM = "waiting_confirm"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class MultiTurnState(TypedDict):
    """多轮对话工作流状态"""
    # 对话历史：使用 Annotated + operator.add 实现追加写入
    messages: Annotated[List[Dict[str, str]], operator.add]

    # 当前输入
    user_input: str
    session_id: str

    # 意图识别
    intent: Optional[Dict[str, Any]]
    intent_confidence: float
    intent_reasoning: str

    # 合同相关
    contract_text: Optional[str]
    contract_type: str

    # Agent执行结果
    agent_results: Dict[str, Any]

    # 对话状态
    status: str
    turn_count: int

    # 配置
    enable_human_review: bool

    # 响应
    response: Optional[str]

    # 错误信息
    error: Optional[str]


# ============================================================
# 意图到Agent的映射
# ============================================================

INTENT_REQUIRED_AGENTS = {
    IntentType.CONTRACT_REVIEW.value: [
        "document_parser", "risk_assessor", "clause_analyst",
        "compliance_checker", "report_generator"
    ],
    IntentType.RISK_ASSESSMENT.value: ["risk_assessor"],
    IntentType.CLAUSE_ANALYSIS.value: ["clause_analyst"],
    IntentType.COMPLIANCE_CHECK.value: ["compliance_checker"],
    IntentType.REPORT_GENERATION.value: ["report_generator"],
    IntentType.MODIFY_CONTRACT.value: [
        "document_parser", "risk_assessor", "clause_analyst", "compliance_checker"
    ],
    IntentType.TOPIC_RAISE.value: ["risk_assessor", "clause_analyst", "compliance_checker"],
    IntentType.TOPIC_FOLLOW_UP.value: ["risk_assessor", "clause_analyst", "compliance_checker"],
}


# ============================================================
# 条件判断函数
# ============================================================

def should_continue_loop(state: MultiTurnState) -> str:
    """判断对话是否继续循环

    所有输入都回到 process_user_input 走全流程，由意图识别决定路由。
    只有出错时才强制结束。
    """
    if state.get("error"):
        return "end"
    return "loop"


def should_end_after_response(state: MultiTurnState) -> str:
    """generate_response 之后判断是否结束对话

    - 结束意图(farewell) → end
    - 人工审批被取消 → end
    - 其他 → wait（进入等待用户输入）
    """
    intent = state.get("intent", {})
    intent_type = intent.get("type", "")

    # 结束意图 → 直接结束
    if intent_type == IntentType.FAREWELL.value:
        return "end"

    # 人工审批被取消 → 结束
    if state.get("status") == ConversationStatus.CANCELLED.value:
        return "end"

    return "wait"


# ============================================================
# 节点函数
# ============================================================

def create_node_functions():
    """创建节点函数（工厂模式，复用Agent实例）"""

    intent_recognizer = IntentRecognizer()
    parser = DocumentParserAgent()
    clause_analyst = ClauseAnalysisAgent()
    risk_assessor = RiskAssessmentAgent()
    compliance_checker = ComplianceCheckerAgent()
    report_generator = ReportGeneratorAgent()

    agent_instances = {
        "document_parser": parser,
        "clause_analyst": clause_analyst,
        "risk_assessor": risk_assessor,
        "compliance_checker": compliance_checker,
        "report_generator": report_generator,
    }

    async def process_user_input(state: MultiTurnState) -> MultiTurnState:
        """处理用户输入节点"""
        from datetime import datetime

        user_input = state.get("user_input", "")
        state["status"] = ConversationStatus.COLLECTING.value
        state["turn_count"] = state.get("turn_count", 0) + 1
        # 清空上一轮的 response 和 error（不清空 agent_results，追问时可复用）
        state["response"] = None
        state["error"] = None

        logger.info(f"处理用户输入: {user_input[:50]}..., turn={state['turn_count']}")
        # operator.add 语义：返回的列表元素会被追加到历史列表末尾
        return {
            **state,
            "messages": [{
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat(),
            }],
        }

    async def recognize_intent(state: MultiTurnState) -> MultiTurnState:
        """意图识别节点"""
        user_input = state.get("user_input", "")

        # 构建上下文
        context = {
            "last_intent": state.get("intent", {}).get("type") if state.get("intent") else None,
            "has_contract_text": bool(state.get("contract_text")),
            "turn_count": state.get("turn_count", 0),
        }

        try:
            intent = await intent_recognizer.recognize(user_input, context)
            state["intent"] = intent.to_dict()
            state["intent_confidence"] = intent.confidence
            state["intent_reasoning"] = intent.reasoning
            state["status"] = ConversationStatus.PROCESSING.value

            logger.info(f"意图识别完成: {intent.type.value} (confidence={intent.confidence:.2f})")
        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            state["error"] = f"意图识别失败: {str(e)}"
            state["intent"] = {"type": IntentType.UNKNOWN.value, "confidence": 0.0}

        return state

    async def route_by_intent(state: MultiTurnState) -> str:
        """根据意图类型路由"""
        intent = state.get("intent", {})
        intent_type = intent.get("type", IntentType.UNKNOWN.value)

        # 意图到处理路径的映射
        route_map = {
            IntentType.CONTRACT_REVIEW.value: "analysis",
            IntentType.RISK_ASSESSMENT.value: "analysis",
            IntentType.CLAUSE_ANALYSIS.value: "analysis",
            IntentType.COMPLIANCE_CHECK.value: "analysis",
            IntentType.MODIFY_CONTRACT.value: "analysis",
            IntentType.REPORT_GENERATION.value: "analysis",
            IntentType.QUESTION_ANSWER.value: "follow_up",
            IntentType.TOPIC_RAISE.value: "topic",
            IntentType.TOPIC_FOLLOW_UP.value: "topic",
            IntentType.GREETING.value: "direct",
            IntentType.FAREWELL.value: "direct",
            IntentType.UNKNOWN.value: "direct",
        }

        route = route_map.get(intent_type, "direct")
        logger.info(f"意图路由: {intent_type} → {route}")
        return route

    async def execute_analysis_agents(state: MultiTurnState) -> MultiTurnState:
        """执行分析类Agent

        分阶段执行：先串行执行 document_parser，再并行执行其余 Agent
        """
        intent = state.get("intent", {})
        intent_type = intent.get("type", IntentType.UNKNOWN.value)

        # 检查是否需要合同文本
        requires_contract = intent_type in [
            IntentType.CONTRACT_REVIEW.value, IntentType.RISK_ASSESSMENT.value,
            IntentType.CLAUSE_ANALYSIS.value, IntentType.COMPLIANCE_CHECK.value,
            IntentType.MODIFY_CONTRACT.value,
        ]

        if requires_contract and not state.get("contract_text"):
            state["response"] = "请先上传或提供合同文本，然后我再帮您进行分析。"
            state["status"] = ConversationStatus.COMPLETED.value
            return state

        # 获取需要执行的Agent列表
        required_agents = INTENT_REQUIRED_AGENTS.get(intent_type, [])
        if not required_agents:
            state["response"] = f"不支持的意图类型: {intent_type}"
            state["status"] = ConversationStatus.ERROR.value
            return state

        all_results = {}

        # === 第一阶段：串行执行 document_parser ===
        if "document_parser" in required_agents and "document_parser" in agent_instances:
            agent = agent_instances["document_parser"]
            task = {
                "contract_text": state.get("contract_text", ""),
                "contract_type": state.get("contract_type", "general"),
                "review_focus": [],
                "session_id": state.get("session_id", ""),
                "previous_results": {},
            }
            try:
                result = await agent.process(task)
                all_results["document_parser"] = result
            except Exception as e:
                logger.error(f"Agent document_parser 执行失败: {e}")
                all_results["document_parser"] = {"error": str(e)}

        # === 第二阶段：并行执行其余 Agent（它们可以基于原始合同文本工作）===
        parallel_agents = [a for a in required_agents if a != "document_parser"]
        tasks = []
        for agent_name in parallel_agents:
            if agent_name in agent_instances:
                agent = agent_instances[agent_name]
                task = {
                    "contract_text": state.get("contract_text", ""),
                    "contract_type": state.get("contract_type", "general"),
                    "review_focus": [],
                    "session_id": state.get("session_id", ""),
                    "previous_results": all_results,
                }
                tasks.append((agent_name, agent.process(task)))

        if tasks:
            results = await asyncio.gather(
                *[t[1] for t in tasks],
                return_exceptions=True
            )
            for (agent_name, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"Agent {agent_name} 执行失败: {result}")
                    all_results[agent_name] = {"error": str(result)}
                else:
                    all_results[agent_name] = result

        # 增量合并：保留历史分析结果，新的覆盖同名 key
        existing_results = state.get("agent_results", {})
        existing_results.update(all_results)
        state["agent_results"] = existing_results
        state["status"] = ConversationStatus.COMPLETED.value

        logger.info(f"Agent执行完成: {list(all_results.keys())}")
        return state

    async def handle_follow_up(state: MultiTurnState) -> MultiTurnState:
        """处理追问和问题回答"""
        user_input = state.get("user_input", "")
        contract_text = state.get("contract_text", "")
        messages = state.get("messages", [])

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            # 构建上下文
            context_parts = []

            if contract_text:
                truncated = contract_text[:15000] if len(contract_text) > 15000 else contract_text
                context_parts.append(f"=== 合同内容 ===\n{truncated}")

            context_parts.append("\n=== 对话历史 ===")
            for msg in messages[-10:]:  # 最近10条消息
                role = "用户" if msg["role"] == "user" else "助手"
                context_parts.append(f"{role}: {msg['content'][:500]}")

            context_str = "\n".join(context_parts)

            llm = get_llm()
            llm_messages = [
                SystemMessage(content="""你是一个合同审查助手。用户之前已经对合同进行了分析，现在在追问细节。

规则：
1. 仔细阅读合同全文内容，找到与用户问题相关的条款
2. 对话历史中助手的回复包含了之前的分析结果，可直接引用
3. 如果合同中有明确条款回答用户问题，必须引用具体条款内容
4. 回答要简洁明了，直接回答问题
5. 只有在合同全文中确实找不到相关信息时才说"未发现"
6. 如果合同被修改过（如新增条款），修改后的内容在合同文本中可以找到
7. 如果用户追问某个具体风险点（如"分析一下无限责任风险"），需要：
   - 从之前的分析结果中找到该风险点的详细信息
   - 结合合同具体内容，给出该风险的详细分析
   - 包括：风险描述、影响、相关条款、修改建议
8. 回答要结构化，使用清晰的标题和列表"""),
                HumanMessage(content=f"""{context_str}

用户问题：{user_input}""")
            ]

            response = await llm.ainvoke(llm_messages)
            state["response"] = response.content
            state["status"] = ConversationStatus.COMPLETED.value

        except Exception as e:
            logger.error(f"追问处理失败: {e}")
            state["error"] = f"回答问题时出现错误: {str(e)}"
            state["status"] = ConversationStatus.ERROR.value

        return state

    async def handle_topic_discussion(state: MultiTurnState) -> MultiTurnState:
        """处理议题讨论"""
        user_input = state.get("user_input", "")
        contract_text = state.get("contract_text", "")

        if not contract_text:
            state["response"] = "请先上传合同文本，然后我才能帮您讨论具体问题。"
            state["status"] = ConversationStatus.COMPLETED.value
            return state

        try:
            # 创建议题
            topic = TopicBoard().create_topic(user_input, raised_by="user")

            # 选择参与Agent
            participants = ["risk_assessor", "clause_analyst", "compliance_checker"]

            # 并行调用Agent讨论
            tasks = []
            for agent_name in participants:
                if agent_name in agent_instances:
                    agent = agent_instances[agent_name]
                    tasks.append(agent.discuss_topic(topic))

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # 收集有效回应
            valid_responses = []
            for resp in responses:
                if isinstance(resp, TopicResponse):
                    valid_responses.append(resp)

            # 生成综合结论
            conclusion = await _generate_topic_conclusion(topic, valid_responses)

            # 格式化回复
            response = _format_topic_response(topic, valid_responses, conclusion)
            state["response"] = response
            state["status"] = ConversationStatus.COMPLETED.value

        except Exception as e:
            logger.error(f"议题讨论失败: {e}")
            state["error"] = f"议题讨论时出现错误: {str(e)}"
            state["status"] = ConversationStatus.ERROR.value

        return state

    async def generate_response(state: MultiTurnState) -> MultiTurnState:
        """生成最终回复"""
        from datetime import datetime

        # 如果已经有response（从其他节点），直接使用
        if not state.get("response"):
            # 根据Agent结果生成回复
            intent = state.get("intent", {})
            intent_type = intent.get("type", IntentType.UNKNOWN.value)
            results = state.get("agent_results", {})
            state["response"] = _format_response(intent_type, results)

        # operator.add 语义：只返回新消息，框架自动追加到历史
        return {
            **state,
            "messages": [{
                "role": "assistant",
                "content": state["response"],
                "timestamp": datetime.now().isoformat(),
            }],
        }

    async def human_review(state: MultiTurnState) -> MultiTurnState:
        """人工审批节点（可选）"""
        if not state.get("enable_human_review"):
            return state

        analysis_summary = {
            "intent": state.get("intent", {}).get("type"),
            "agent_results_count": len(state.get("agent_results", {})),
            "turn_count": state.get("turn_count", 0),
        }

        # interrupt() 会暂停图执行
        approved = interrupt({
            "message": "是否继续执行？",
            "analysis_summary": analysis_summary,
        })

        if not approved:
            state["status"] = ConversationStatus.CANCELLED.value
            state["response"] = "操作已取消。"
            state["error"] = "用户取消执行"

        return state

    async def wait_for_user_input(state: MultiTurnState) -> MultiTurnState:
        """中断并等待用户输入

        每次回复后都触发 interrupt，暂停图执行，等待用户下一条输入。
        恢复后用户输入会写入 state["user_input"]，由 should_continue_loop 判断是否继续。
        """
        # 无条件 interrupt，暂停等待用户输入
        user_reply = interrupt({
            "message": "如需继续提问或补充信息，请告诉我。",
            "awaiting_follow_up": True,
        })

        # 恢复执行时，将用户新输入写入状态
        state["user_input"] = user_reply
        return state

    return {
        "process_user_input": process_user_input,
        "recognize_intent": recognize_intent,
        "route_by_intent": route_by_intent,
        "execute_analysis_agents": execute_analysis_agents,
        "handle_follow_up": handle_follow_up,
        "handle_topic_discussion": handle_topic_discussion,
        "generate_response": generate_response,
        "human_review": human_review,
        "wait_for_user_input": wait_for_user_input,
    }


# ============================================================
# 辅助函数
# ============================================================

async def _generate_topic_conclusion(topic, responses: List) -> str:
    """用LLM综合各Agent的观点，生成结论"""
    if not responses:
        return "暂无分析意见。"

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        opinions_text = ""
        for resp in responses:
            opinions_text += f"\n**{resp.agent_name}** (置信度: {resp.confidence}):\n{resp.opinion}\n"
            if resp.references:
                opinions_text += f"  引用: {', '.join(resp.references)}\n"

        llm = get_llm()
        messages = [
            SystemMessage(content="""你是一个合同审查总监。多个审查专家针对用户的问题给出了各自的专业意见。
请综合各方观点，给出一个清晰的结论。

结论应包含：
1. 共识点（各专家一致同意的观点）
2. 分歧点（如果有不同意见）
3. 综合建议

结论要简洁明了，直接回答用户的问题。"""),
            HumanMessage(content=f"""议题：{topic.content}

各方意见：{opinions_text}

请给出综合结论："""),
        ]

        response = await llm.ainvoke(messages)
        return response.content

    except Exception as e:
        logger.error(f"生成议题结论失败: {e}")
        return "综合分析完成，但生成结论时出现错误。请参考上方各专家的意见。"


def _format_topic_response(topic, responses: List, conclusion: str) -> str:
    """格式化议题讨论结果"""
    lines = [f"## 💬 议题讨论: {topic.title}\n"]

    agent_icons = {
        "risk_assessor": "🔴",
        "clause_analyst": "📝",
        "compliance_checker": "✅",
    }

    for resp in responses:
        icon = agent_icons.get(resp.agent_id, "🤖")
        conf_bar = "●" * int(resp.confidence * 5) + "○" * (5 - int(resp.confidence * 5))
        lines.append(f"### {icon} {resp.agent_name}")
        lines.append(f"置信度: {conf_bar} ({resp.confidence:.0%})\n")
        lines.append(resp.opinion)
        if resp.references:
            lines.append(f"\n📎 引用: {', '.join(resp.references)}")
        lines.append("")

    if conclusion:
        lines.append("---\n")
        lines.append("### 📋 综合结论\n")
        lines.append(conclusion)

    return "\n".join(lines)


def _format_response(intent_type: str, results: Dict[str, Any]) -> str:
    """根据意图类型和Agent结果生成用户友好的回复"""
    # 结束对话 - 无需 Agent 结果
    if intent_type == IntentType.FAREWELL.value:
        return "感谢您的使用！如有需要，随时可以上传新的合同进行审查。再见！👋"

    # 问候 - 无需 Agent 结果
    if intent_type == IntentType.GREETING.value:
        return "您好！我是合同审查助手。请上传合同文件，我可以帮您分析风险、检查合规、生成报告。"

    if not results:
        return "抱歉，处理过程中出现了问题。"

    if intent_type == IntentType.CONTRACT_REVIEW.value:
        completed = [name for name, r in results.items()
                     if isinstance(r, dict) and r.get("status") != "error"]
        failed = [name for name, r in results.items()
                  if isinstance(r, dict) and r.get("status") == "error"]

        response = f"📋 合同审查完成\n\n"
        response += f"已完成: {len(completed)} 个分析\n"
        if failed:
            response += f"失败: {', '.join(failed)}\n"
        response += "\n如需进一步分析，请告诉我具体需求。"
        return response

    if intent_type == IntentType.RISK_ASSESSMENT.value:
        risk_result = results.get("risk_assessor", {})
        if isinstance(risk_result, dict) and "risk_level" in risk_result:
            risk_level = risk_result.get("risk_level", "unknown")
            risks = risk_result.get("risks", [])
            level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_level, "⚪")
            response = f"⚠️ 风险评估完成 {level_emoji}\n\n"
            response += f"风险等级: {risk_level.upper()}\n\n"

            for i, risk in enumerate(risks[:5], 1):
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk.get("severity"), "⚪")
                response += f"{i}. {emoji} {risk.get('name', '无描述')}\n"

            response += "\n如需详细分析某个风险点，请告诉我。"
            return response

    if intent_type == IntentType.CLAUSE_ANALYSIS.value:
        clause_result = results.get("clause_analyst", {})
        if isinstance(clause_result, dict):
            issues = clause_result.get("issues_found", 0)
            return f"📋 条款分析完成\n\n发现问题: {issues} 个\n\n如需详细分析，请告诉我。"

    if intent_type == IntentType.COMPLIANCE_CHECK.value:
        compliance_result = results.get("compliance_checker", {})
        if isinstance(compliance_result, dict):
            score = compliance_result.get("score", 0)
            violations = compliance_result.get("compliance_violations", [])
            response = f"✅ 合规检查完成\n\n合规评分: {score}/100\n\n"
            if violations:
                response += "需要改进:\n"
                for v in violations:
                    response += f"- ⚠️ {v.get('suggestion', '无')}\n"
            else:
                response += "未发现合规问题。\n"
            return response

    return f"已处理您的请求（意图: {intent_type}）。如需其他帮助，请告诉我。"


# ============================================================
# 工作流构建
# ============================================================

def create_multi_turn_workflow(enable_human_review: bool = False):
    """
    创建多轮对话工作流（闭环循环结构）

    Args:
        enable_human_review: 是否启用人工审批

    Returns:
        编译后的工作流图
    """
    nodes = create_node_functions()

    workflow = StateGraph(MultiTurnState)

    # 添加节点
    workflow.add_node("process_user_input", nodes["process_user_input"])
    workflow.add_node("recognize_intent", nodes["recognize_intent"])
    workflow.add_node("execute_analysis_agents", nodes["execute_analysis_agents"])
    workflow.add_node("handle_follow_up", nodes["handle_follow_up"])
    workflow.add_node("handle_topic_discussion", nodes["handle_topic_discussion"])
    workflow.add_node("generate_response", nodes["generate_response"])
    workflow.add_node("wait_for_user_input", nodes["wait_for_user_input"])

    if enable_human_review:
        workflow.add_node("human_review", nodes["human_review"])

    # 入口
    workflow.set_entry_point("process_user_input")

    # 主链路：输入处理 → 意图识别
    workflow.add_edge("process_user_input", "recognize_intent")

    # 意图路由
    workflow.add_conditional_edges(
        "recognize_intent",
        nodes["route_by_intent"],
        {
            "analysis": "execute_analysis_agents",
            "follow_up": "handle_follow_up",
            "topic": "handle_topic_discussion",
            "direct": "generate_response",
        }
    )

    # 各分支汇聚到 generate_response
    workflow.add_edge("execute_analysis_agents", "generate_response")
    workflow.add_edge("handle_follow_up", "generate_response")
    workflow.add_edge("handle_topic_discussion", "generate_response")

    # generate_response → [human_review] → should_end_after_response → END | wait_for_user_input
    if enable_human_review:
        workflow.add_edge("generate_response", "human_review")
        # human_review 之后判断是否结束
        workflow.add_conditional_edges(
            "human_review",
            should_end_after_response,
            {
                "end": END,
                "wait": "wait_for_user_input",
            }
        )
    else:
        # generate_response 之后直接判断是否结束
        workflow.add_conditional_edges(
            "generate_response",
            should_end_after_response,
            {
                "end": END,
                "wait": "wait_for_user_input",
            }
        )

    # wait_for_user_input → 条件边：继续循环 or 结束
    workflow.add_conditional_edges(
        "wait_for_user_input",
        should_continue_loop,
        {
            "loop": "process_user_input",  # 继续：回到输入处理节点，开启下一轮
            "end": END,                     # 结束：退出图
        }
    )

    # Checkpoint
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# 工作流封装类
# ============================================================

class MultiTurnWorkflow:
    """
    多轮对话工作流封装类

    支持：
    - Checkpoint: 每个session_id的状态自动持久化
    - 流式输出: 实时推送执行进度
    - Human-in-the-loop: 可选的人工审批
    """

    def __init__(self, enable_human_review: bool = False):
        self._enable_human_review = enable_human_review
        self._workflow = None

    def _ensure_workflow(self):
        """确保工作流已初始化"""
        if self._workflow is None:
            self._workflow = create_multi_turn_workflow(self._enable_human_review)

    async def run(
        self,
        user_input: str,
        session_id: str = "default",
        contract_text: Optional[str] = None,
        contract_type: str = "general",
        messages: Optional[List[Dict[str, str]]] = None,
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        """
        执行多轮对话工作流

        首轮对话：传入完整初始状态
        非首轮：调用 resume 恢复执行，不覆盖 checkpoint 状态

        Args:
            user_input: 用户输入
            session_id: 会话ID
            contract_text: 合同文本
            contract_type: 合同类型
            messages: 对话历史
            auto_approve: 是否自动审批

        Returns:
            对话结果
        """
        self._ensure_workflow()
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}
        state_snapshot = await self._workflow.aget_state(config)
        is_first_round = state_snapshot.values is None or not state_snapshot.values

        if is_first_round:
            # 首轮对话：传入完整初始状态
            initial_state = MultiTurnState(
                messages=messages or [],
                user_input=user_input,
                session_id=session_id,
                intent=None,
                intent_confidence=0.0,
                intent_reasoning="",
                contract_text=contract_text,
                contract_type=contract_type,
                agent_results={},
                status=ConversationStatus.IDLE.value,
                turn_count=0,
                enable_human_review=self._enable_human_review,
                response=None,
                error=None,
            )
            result = await self._workflow.ainvoke(initial_state, config)
        else:
            # 非首轮：恢复执行，不覆盖历史状态
            return await self.resume(session_id, user_input)

        # 统一处理中断返回
        if isinstance(result, dict) and "__interrupt__" in result:
            interrupt_val = result["__interrupt__"][0].value
            return {
                "status": "awaiting_input",
                "message": interrupt_val.get("message", ""),
                "response": result.get("response", ""),
            }

        return result

    async def stream(
        self,
        user_input: str,
        session_id: str = "default",
        contract_text: Optional[str] = None,
        contract_type: str = "general",
        messages: Optional[List[Dict[str, str]]] = None,
    ):
        """
        流式执行多轮对话工作流

        首轮对话：传入完整初始状态
        非首轮：自动切换为流式恢复

        Args:
            user_input: 用户输入
            session_id: 会话ID
            contract_text: 合同文本
            contract_type: 合同类型
            messages: 对话历史

        Yields:
            事件字典
        """
        self._ensure_workflow()
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}

        # 检查会话是否已存在
        state_snapshot = await self._workflow.aget_state(config)
        is_first_round = state_snapshot.values is None or not state_snapshot.values

        if not is_first_round:
            # 非首轮：使用流式恢复
            async for event in self.stream_resume(session_id, user_input):
                yield event
            return

        # 首轮对话：传入完整初始状态
        initial_state = MultiTurnState(
            messages=messages or [],
            user_input=user_input,
            session_id=session_id,
            intent=None,
            intent_confidence=0.0,
            intent_reasoning="",
            contract_text=contract_text,
            contract_type=contract_type,
            agent_results={},
            status=ConversationStatus.IDLE.value,
            turn_count=0,
            enable_human_review=self._enable_human_review,
            response=None,
            error=None,
        )

        yield {"event": "progress", "data": {"status": "starting", "message": "开始处理..."}}

        async for event in self._workflow.astream(initial_state, config):
            parsed = await self._parse_stream_event(event)
            if parsed is not None:
                yield parsed

        yield {"event": "done", "data": {}}

    async def stream_resume(self, session_id: str, user_reply: str):
        """
        流式恢复被 interrupt 暂停的工作流

        Args:
            session_id: 会话ID
            user_reply: 用户回复内容

        Yields:
            事件字典
        """
        self._ensure_workflow()
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}

        yield {"event": "progress", "data": {"status": "resuming", "message": "恢复对话中..."}}

        async for event in self._workflow.astream(
            Command(resume=user_reply),
            config,
        ):
            parsed = await self._parse_stream_event(event)
            if parsed is not None:
                yield parsed

        yield {"event": "done", "data": {}}

    async def _parse_stream_event(self, event) -> Dict[str, Any]:
        """解析流式事件，统一 stream 和 stream_resume 的事件处理逻辑"""
        if not isinstance(event, dict):
            return None

        if "process_user_input" in event:
            return {"event": "progress", "data": {"status": "input_processed", "message": "用户输入已处理"}}

        elif "recognize_intent" in event:
            intent = event["recognize_intent"].get("intent", {})
            return {"event": "progress", "data": {
                "status": "intent_recognized",
                "intent": intent.get("type"),
                "confidence": intent.get("confidence", 0),
                "message": f"意图识别完成: {intent.get('type', 'unknown')}"
            }}

        elif "execute_analysis_agents" in event:
            return {"event": "progress", "data": {"status": "agents_executing", "message": "正在执行分析..."}}

        elif "handle_follow_up" in event:
            return {"event": "progress", "data": {"status": "answering", "message": "正在回答问题..."}}

        elif "handle_topic_discussion" in event:
            return {"event": "progress", "data": {"status": "discussing", "message": "正在进行议题讨论..."}}

        elif "generate_response" in event:
            response = event["generate_response"].get("response", "")
            if response:
                return {"event": "result", "data": {"content": response}}

        elif "human_review" in event:
            return {"event": "interrupt", "data": event["human_review"]}

        elif "wait_for_user_input" in event:
            return {"event": "interrupt", "data": {
                "type": "awaiting_follow_up",
                "message": "如需继续提问或补充信息，请告诉我。",
            }}

        return None

    async def resume(self, session_id: str, user_reply) -> Dict[str, Any]:
        """
        恢复被 interrupt 暂停的工作流

        使用 Command(resume=...) 恢复执行，用户输入会注入到
        wait_for_user_input 节点的 interrupt() 返回值中。

        Args:
            session_id: 会话ID
            user_reply: 用户的回复内容

        Returns:
            对话结果
        """
        self._ensure_workflow()
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}
        result = await self._workflow.ainvoke(
            Command(resume=user_reply),
            config,
        )

        # 检查是否有新的 interrupt（下一轮等待输入）
        if isinstance(result, dict) and "__interrupt__" in result:
            interrupt_val = result["__interrupt__"][0].value
            return {
                "status": "awaiting_input",
                "message": interrupt_val.get("message", ""),
                "response": result.get("response", ""),
            }

        return result

    def get_workflow_info(self) -> Dict[str, Any]:
        """获取工作流信息"""
        return {
            "name": "多轮对话工作流",
            "version": "2.0.0",
            "description": "基于LangGraph的多轮对话工作流，支持闭环循环、Checkpoint、流式输出、Human-in-the-loop",
            "features": {
                "checkpoint": "MemorySaver状态持久化，支持断点恢复",
                "streaming": "实时流式输出执行进度",
                "human_in_the_loop": "可选的人工审批功能",
                "loop": "interrupt + Command(resume=...) 实现闭环多轮对话",
            },
            "nodes": [
                "process_user_input",
                "recognize_intent",
                "execute_analysis_agents",
                "handle_follow_up",
                "handle_topic_discussion",
                "generate_response",
                "human_review (可选)",
                "wait_for_user_input",
            ],
        }
