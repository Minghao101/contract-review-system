"""
合同审查工作流 - 基于 LangGraph 的状态图实现（高级特性版）

高级特性：
1. Checkpoint (MemorySaver) — 状态持久化，支持断点恢复
2. Human-in-the-loop (interrupt) — 报告生成前插入人工审批
3. Subgraph — 并行分析封装为子图

工作流拓扑:
  START → route_by_intent → parse_document → after_parse → parallel_analysis(子图) → human_review → generate_report → END
                                                  ↓ (单维度)
                                             assess_risk / analyze_clauses / check_compliance → END

子图内部:
  assess_risk ──┐
  analyze_clauses ──┼──→ merge_results
  check_compliance ─┘
"""
import asyncio
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from src.agents.document_parser_agent import DocumentParserAgent
from src.agents.clause_analysis_agent import ClauseAnalysisAgent
from src.agents.risk_assessment_agent import RiskAssessmentAgent
from src.agents.compliance_checker_agent import ComplianceCheckerAgent
from src.agents.report_generator_agent import ReportGeneratorAgent


class ReviewStatus(str, Enum):
    """审查状态"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ============================================================
# 主图状态
# ============================================================

class ReviewState(TypedDict):
    """主图工作流状态"""
    # 输入
    contract_text: str
    contract_type: str
    review_focus: List[str]
    intent_type: str
    session_id: str

    # 各阶段结果
    parse_result: Optional[Dict[str, Any]]
    clause_result: Optional[Dict[str, Any]]
    risk_result: Optional[Dict[str, Any]]
    compliance_result: Optional[Dict[str, Any]]
    report_result: Optional[Dict[str, Any]]

    # 状态控制
    status: str
    error: Optional[str]
    steps_completed: List[str]


# ============================================================
# 子图状态（并行分析）
# ============================================================

class AnalysisSubgraphState(TypedDict):
    """并行分析子图状态"""
    contract_text: str
    contract_type: str
    clause_result: Optional[Dict[str, Any]]
    risk_result: Optional[Dict[str, Any]]
    compliance_result: Optional[Dict[str, Any]]


# ============================================================
# 条件路由函数
# ============================================================

def route_by_intent(state: ReviewState) -> str:
    """根据意图类型路由到不同的执行路径"""
    intent = state.get("intent_type", "contract_review")

    route_map = {
        "contract_review": "full_review",
        "risk_assessment": "single_risk",
        "clause_analysis": "single_clause",
        "compliance_check": "single_compliance",
        "report_generation": "report_only",
        "modify_contract": "incremental_modify",
    }

    return route_map.get(intent, "full_review")


def after_parse(state: ReviewState) -> str:
    """解析后路由：根据意图决定下一步"""
    if state.get("status") == ReviewStatus.FAILED.value:
        return "end"
    intent = state.get("intent_type", "contract_review")
    route_map = {
        "contract_review": "parallel",
        "risk_assessment": "risk",
        "clause_analysis": "clause",
        "compliance_check": "compliance",
        "modify_contract": "parallel",
    }
    return route_map.get(intent, "parallel")


# ============================================================
# 子图：并行分析（risk + clause + compliance）
# ============================================================

def create_analysis_subgraph():
    """
    创建并行分析子图

    子图内部结构:
      assess_risk ──┐
      analyze_clauses ──┼──→ merge_results
      check_compliance ─┘
    """
    parser = DocumentParserAgent()
    clause_analyst = ClauseAnalysisAgent()
    risk_assessor = RiskAssessmentAgent()
    compliance_checker = ComplianceCheckerAgent()

    async def assess_risk(state: AnalysisSubgraphState) -> AnalysisSubgraphState:
        """风险评估节点"""
        try:
            task = {
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general"),
            }
            result = await risk_assessor.process(task)
            state["risk_result"] = result
        except Exception as e:
            state["risk_result"] = {"error": str(e), "risk_level": "unknown", "risks": []}
        return state

    async def analyze_clauses(state: AnalysisSubgraphState) -> AnalysisSubgraphState:
        """条款分析节点"""
        try:
            task = {
                "contract_text": state["contract_text"],
                "review_focus": [],
            }
            result = await clause_analyst.process(task)
            state["clause_result"] = result
        except Exception as e:
            state["clause_result"] = {"error": str(e), "issues": []}
        return state

    async def check_compliance(state: AnalysisSubgraphState) -> AnalysisSubgraphState:
        """合规检查节点"""
        try:
            task = {
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general"),
            }
            result = await compliance_checker.process(task)
            state["compliance_result"] = result
        except Exception as e:
            state["compliance_result"] = {"error": str(e), "compliance_status": "unknown"}
        return state

    async def merge_results(state: AnalysisSubgraphState) -> AnalysisSubgraphState:
        """合并结果（汇聚节点）"""
        # 三个分析结果已在各自节点中写入 state，此处无需额外操作
        return state

    # 构建子图
    subgraph = StateGraph(AnalysisSubgraphState)

    subgraph.add_node("assess_risk", assess_risk)
    subgraph.add_node("analyze_clauses", analyze_clauses)
    subgraph.add_node("check_compliance", check_compliance)
    subgraph.add_node("merge_results", merge_results)

    # 三个分析并行执行，然后汇聚
    subgraph.add_edge("assess_risk", "merge_results")
    subgraph.add_edge("analyze_clauses", "merge_results")
    subgraph.add_edge("check_compliance", "merge_results")

    # 入口：三个节点并行（LangGraph 会自动并行执行无入边的节点）
    subgraph.set_entry_point("assess_risk")
    subgraph.set_entry_point("analyze_clauses")
    subgraph.set_entry_point("check_compliance")
    subgraph.set_finish_point("merge_results")

    return subgraph.compile()


# ============================================================
# 主图节点函数
# ============================================================

def create_node_functions():
    """创建节点函数（工厂模式，复用 Agent 实例）"""

    parser = DocumentParserAgent()
    report_generator = ReportGeneratorAgent()
    analysis_subgraph = create_analysis_subgraph()

    async def parse_document(state: ReviewState) -> ReviewState:
        """解析文档节点"""
        try:
            task = {
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general"),
            }
            result = await parser.process(task)
            state["parse_result"] = result
            state["steps_completed"].append("parse_document")

            if "error" in result:
                state["status"] = ReviewStatus.FAILED.value
                state["error"] = result["error"]
            else:
                state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.FAILED.value
            state["error"] = f"文档解析失败: {str(e)}"

        return state

    async def parallel_analysis(state: ReviewState) -> ReviewState:
        """调用并行分析子图"""
        try:
            sub_state = {
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general"),
                "clause_result": None,
                "risk_result": None,
                "compliance_result": None,
            }
            result = await analysis_subgraph.ainvoke(sub_state)

            state["clause_result"] = result.get("clause_result")
            state["risk_result"] = result.get("risk_result")
            state["compliance_result"] = result.get("compliance_result")
            state["steps_completed"].append("parallel_analysis")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"并行分析失败: {str(e)}"

        return state

    async def human_review(state: ReviewState) -> ReviewState:
        """
        人工审批节点 — Human-in-the-loop

        使用 interrupt() 暂停图执行，将分析摘要返回给前端。
        用户通过 Command(resume=True/False) 恢复执行。
        """
        analysis_summary = {
            "risk_level": (state.get("risk_result") or {}).get("risk_level", "unknown"),
            "compliance_status": (state.get("compliance_result") or {}).get("compliance_status", "unknown"),
            "clause_issues_count": len((state.get("clause_result") or {}).get("issues", [])),
        }

        # interrupt() 会暂停图执行，返回 value 给调用方
        approved = interrupt({
            "message": "分析已完成，请确认是否生成报告",
            "analysis_summary": analysis_summary,
        })

        # 用户通过 Command(resume=True) 恢复后，approved = True
        if not approved:
            state["status"] = ReviewStatus.FAILED.value
            state["error"] = "用户拒绝生成报告"
            return state

        state["steps_completed"].append("human_review")
        return state

    async def generate_report(state: ReviewState) -> ReviewState:
        """生成报告节点"""
        try:
            previous_results = {}
            if state.get("parse_result"):
                previous_results["document_parser"] = {"result": state["parse_result"]}
            if state.get("clause_result"):
                previous_results["clause_analyst"] = {"result": state["clause_result"]}
            if state.get("risk_result"):
                previous_results["risk_assessor"] = {"result": state["risk_result"]}
            if state.get("compliance_result"):
                previous_results["compliance_checker"] = {"result": state["compliance_result"]}

            result = await report_generator.process({
                "previous_results": previous_results,
                "session_id": state.get("session_id", ""),
            })
            state["report_result"] = result
            state["steps_completed"].append("generate_report")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"报告生成失败: {str(e)}"

        return state

    # 单 Agent 节点（用于单维度分析）
    risk_assessor = RiskAssessmentAgent()
    clause_analyst = ClauseAnalysisAgent()
    compliance_checker = ComplianceCheckerAgent()

    async def assess_risk(state: ReviewState) -> ReviewState:
        try:
            task = {"contract_text": state["contract_text"], "contract_type": state.get("contract_type", "general")}
            result = await risk_assessor.process(task)
            state["risk_result"] = result
            state["steps_completed"].append("assess_risk")
            state["status"] = ReviewStatus.COMPLETED.value
        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"风险评估失败: {str(e)}"
        return state

    async def analyze_clauses(state: ReviewState) -> ReviewState:
        try:
            task = {"contract_text": state["contract_text"], "review_focus": state.get("review_focus", [])}
            result = await clause_analyst.process(task)
            state["clause_result"] = result
            state["steps_completed"].append("analyze_clauses")
            state["status"] = ReviewStatus.COMPLETED.value
        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"条款分析失败: {str(e)}"
        return state

    async def check_compliance(state: ReviewState) -> ReviewState:
        try:
            task = {"contract_text": state["contract_text"], "contract_type": state.get("contract_type", "general")}
            result = await compliance_checker.process(task)
            state["compliance_result"] = result
            state["steps_completed"].append("check_compliance")
            state["status"] = ReviewStatus.COMPLETED.value
        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"合规检查失败: {str(e)}"
        return state

    return {
        "parse_document": parse_document,
        "parallel_analysis": parallel_analysis,
        "human_review": human_review,
        "generate_report": generate_report,
        "assess_risk": assess_risk,
        "analyze_clauses": analyze_clauses,
        "check_compliance": check_compliance,
    }


# ============================================================
# 主图构建
# ============================================================

def create_review_workflow():
    """
    创建合同审查工作流（支持 Checkpoint + Human-in-the-loop + Subgraph）

    Returns:
        编译后的工作流图（带 MemorySaver checkpointer）
    """
    nodes = create_node_functions()

    workflow = StateGraph(ReviewState)

    # 添加节点
    workflow.add_node("parse_document", nodes["parse_document"])
    workflow.add_node("parallel_analysis", nodes["parallel_analysis"])
    workflow.add_node("human_review", nodes["human_review"])
    workflow.add_node("generate_report", nodes["generate_report"])

    # 单 Agent 节点（用于单维度分析）
    workflow.add_node("assess_risk", nodes["assess_risk"])
    workflow.add_node("analyze_clauses", nodes["analyze_clauses"])
    workflow.add_node("check_compliance", nodes["check_compliance"])

    # 入口：根据意图路由
    workflow.set_conditional_entry_point(
        route_by_intent,
        {
            "full_review": "parse_document",
            "single_risk": "parse_document",
            "single_clause": "parse_document",
            "single_compliance": "parse_document",
            "report_only": "generate_report",
            "incremental_modify": "parse_document",
        }
    )

    # parse_document 后的条件路由
    workflow.add_conditional_edges(
        "parse_document",
        after_parse,
        {
            "parallel": "parallel_analysis",
            "risk": "assess_risk",
            "clause": "analyze_clauses",
            "compliance": "check_compliance",
            "end": END,
        }
    )

    # 完整审查路径：parallel_analysis → human_review → generate_report → END
    workflow.add_edge("parallel_analysis", "human_review")

    def after_human_review(state: ReviewState) -> str:
        """人工审批后路由"""
        if state.get("status") == ReviewStatus.FAILED.value:
            return "end"
        return "generate"

    workflow.add_conditional_edges(
        "human_review",
        after_human_review,
        {
            "generate": "generate_report",
            "end": END,
        }
    )
    workflow.add_edge("generate_report", END)

    # 单 Agent 分析后 → 结束
    workflow.add_edge("assess_risk", END)
    workflow.add_edge("analyze_clauses", END)
    workflow.add_edge("check_compliance", END)

    # Checkpoint: 使用 MemorySaver 持久化状态
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# 工作流封装类
# ============================================================

class ContractReviewWorkflow:
    """
    合同审查工作流封装类

    支持：
    - Checkpoint: 每个 session_id 的状态自动持久化
    - Human-in-the-loop: 报告生成前暂停等待用户审批
    - Subgraph: 并行分析封装为子图
    """

    def __init__(self):
        self._workflow = None

    def _ensure_workflow(self):
        """确保工作流已初始化"""
        if self._workflow is None:
            self._workflow = create_review_workflow()

    async def run(
        self,
        contract_text: str,
        contract_type: str = "general",
        review_focus: List[str] = None,
        intent_type: str = "contract_review",
        session_id: str = "default",
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        """
        执行合同审查工作流

        Args:
            contract_text: 合同文本
            contract_type: 合同类型
            review_focus: 审查焦点
            intent_type: 意图类型
            session_id: 会话ID（用作 checkpoint thread_id）
            auto_approve: 是否自动审批（跳过 human_review interrupt）

        Returns:
            审查结果字典
        """
        self._ensure_workflow()

        initial_state = ReviewState(
            contract_text=contract_text,
            contract_type=contract_type,
            review_focus=review_focus or [],
            intent_type=intent_type,
            session_id=session_id,
            parse_result=None,
            clause_result=None,
            risk_result=None,
            compliance_result=None,
            report_result=None,
            status=ReviewStatus.PENDING.value,
            error=None,
            steps_completed=[],
        )

        config = {"configurable": {"thread_id": session_id}}

        if auto_approve:
            # 自动审批模式：执行到 interrupt 时自动 resume
            result = await self._workflow.ainvoke(initial_state, config)

            # 检查是否暂停在 interrupt
            if result.get("status") != ReviewStatus.FAILED.value and "human_review" not in result.get("steps_completed", []):
                # 自动恢复：resume with True
                result = await self._workflow.ainvoke(
                    Command(resume=True),
                    config,
                )

            return result
        else:
            # 手动审批模式：返回 interrupt 信息给前端
            result = await self._workflow.ainvoke(initial_state, config)
            return result

    async def resume(self, session_id: str, approved: bool) -> Dict[str, Any]:
        """
        恢复被 interrupt 暂停的工作流

        Args:
            session_id: 会话ID
            approved: 是否批准生成报告

        Returns:
            审查结果字典
        """
        self._ensure_workflow()
        config = {"configurable": {"thread_id": session_id}}
        result = await self._workflow.ainvoke(
            Command(resume=approved),
            config,
        )
        return result

    def get_workflow_info(self) -> Dict[str, Any]:
        """获取工作流信息"""
        return {
            "name": "合同审查工作流",
            "version": "3.0.0",
            "description": "基于 LangGraph 的合同审查工作流，支持 Checkpoint、Human-in-the-loop、Subgraph",
            "features": {
                "checkpoint": "MemorySaver 状态持久化，支持断点恢复",
                "human_in_the_loop": "报告生成前 interrupt 暂停，等待用户审批",
                "subgraph": "并行分析（risk + clause + compliance）封装为子图",
            },
            "nodes": [
                "parse_document",
                "parallel_analysis (子图)",
                "human_review (interrupt)",
                "generate_report",
                "assess_risk (单维度)",
                "analyze_clauses (单维度)",
                "check_compliance (单维度)",
            ],
            "intent_routes": {
                "contract_review": "parse → parallel_analysis(子图) → human_review → report",
                "risk_assessment": "parse → risk",
                "clause_analysis": "parse → clause",
                "compliance_check": "parse → compliance",
                "report_generation": "report",
                "modify_contract": "parse(增量) → parallel_analysis(子图) → human_review → report",
            },
        }
