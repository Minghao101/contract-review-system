"""
合同审查工作流 - 基于LangGraph的状态图实现

工作流节点:
  START → parse_document → analyze_clauses → assess_risk → check_compliance → generate_report → END

条件路由:
  - 如果parse_document失败 → 直接END
  - 如果check_compliance发现严重违规 → 跳过generate_report直接END
"""
import sys
from pathlib import Path
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from enum import Enum

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

from src.agents import (
    DocumentParserAgent,
    ClauseAnalysisAgent,
    RiskAssessmentAgent,
    ComplianceCheckerAgent,
    ReportGeneratorAgent,
)


class ReviewStatus(str, Enum):
    """审查状态"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ReviewState(TypedDict):
    """工作流状态"""
    contract_text: str
    contract_type: str
    review_focus: List[str]
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
# 条件路由函数（模块级，可在测试中直接导入）
# ============================================================

def should_continue_after_parse(state: ReviewState) -> str:
    """解析后是否继续"""
    if state.get("status") == ReviewStatus.FAILED.value:
        return "end"
    return "continue"


def should_generate_report(state: ReviewState) -> str:
    """是否生成报告"""
    if state.get("status") == ReviewStatus.FAILED.value:
        return "end"
    return "generate"


def create_review_workflow():
    """
    创建合同审查工作流

    Returns:
        编译后的工作流图
    """
    if not HAS_LANGGRAPH:
        raise ImportError("langgraph未安装，请运行: pip install langgraph")

    # 创建Agent实例
    parser = DocumentParserAgent()
    clause_analyst = ClauseAnalysisAgent()
    risk_assessor = RiskAssessmentAgent()
    compliance_checker = ComplianceCheckerAgent()
    report_generator = ReportGeneratorAgent()

    # 定义节点函数
    async def parse_document(state: ReviewState) -> ReviewState:
        """解析文档节点"""
        try:
            result = await parser.process({
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general")
            })
            state["parse_result"] = result
            state["steps_completed"].append("parse_document")

            # 检查是否有错误
            if "error" in result:
                state["status"] = ReviewStatus.FAILED.value
                state["error"] = result["error"]
            else:
                state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.FAILED.value
            state["error"] = f"文档解析失败: {str(e)}"

        return state

    async def analyze_clauses(state: ReviewState) -> ReviewState:
        """条款分析节点"""
        try:
            result = await clause_analyst.process({
                "contract_text": state["contract_text"],
                "review_focus": state.get("review_focus", [])
            })
            state["clause_result"] = result
            state["steps_completed"].append("analyze_clauses")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"条款分析失败: {str(e)}"

        return state

    async def assess_risk(state: ReviewState) -> ReviewState:
        """风险评估节点"""
        try:
            result = await risk_assessor.process({
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general")
            })
            state["risk_result"] = result
            state["steps_completed"].append("assess_risk")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"风险评估失败: {str(e)}"

        return state

    async def check_compliance(state: ReviewState) -> ReviewState:
        """合规检查节点"""
        try:
            result = await compliance_checker.process({
                "contract_text": state["contract_text"],
                "contract_type": state.get("contract_type", "general")
            })
            state["compliance_result"] = result
            state["steps_completed"].append("check_compliance")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"合规检查失败: {str(e)}"

        return state

    async def generate_report(state: ReviewState) -> ReviewState:
        """生成报告节点"""
        try:
            # 收集前序结果
            previous_results = {}
            if state.get("parse_result"):
                previous_results["parse_result"] = state["parse_result"]
            if state.get("clause_result"):
                previous_results["clause_result"] = state["clause_result"]
            if state.get("risk_result"):
                previous_results["risk_result"] = state["risk_result"]
            if state.get("compliance_result"):
                previous_results["compliance_result"] = state["compliance_result"]

            result = await report_generator.process({
                "previous_results": previous_results,
                "contract_text": state["contract_text"]
            })
            state["report_result"] = result
            state["steps_completed"].append("generate_report")
            state["status"] = ReviewStatus.COMPLETED.value

        except Exception as e:
            state["status"] = ReviewStatus.PARTIAL.value
            state["error"] = f"报告生成失败: {str(e)}"

        return state

    # 构建状态图
    workflow = StateGraph(ReviewState)

    # 添加节点
    workflow.add_node("parse_document", parse_document)
    workflow.add_node("analyze_clauses", analyze_clauses)
    workflow.add_node("assess_risk", assess_risk)
    workflow.add_node("check_compliance", check_compliance)
    workflow.add_node("generate_report", generate_report)

    # 设置入口
    workflow.set_entry_point("parse_document")

    # 添加条件边
    workflow.add_conditional_edges(
        "parse_document",
        should_continue_after_parse,
        {
            "continue": "analyze_clauses",
            "end": END
        }
    )

    # 线性边
    workflow.add_edge("analyze_clauses", "assess_risk")
    workflow.add_edge("assess_risk", "check_compliance")

    # 合规检查后的条件边
    workflow.add_conditional_edges(
        "check_compliance",
        should_generate_report,
        {
            "generate": "generate_report",
            "end": END
        }
    )

    # 报告生成后结束
    workflow.add_edge("generate_report", END)

    # 编译
    return workflow.compile()


class ContractReviewWorkflow:
    """
    合同审查工作流封装类

    提供简单接口执行完整审查流程
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
        review_focus: List[str] = None
    ) -> Dict[str, Any]:
        """
        执行合同审查工作流

        Args:
            contract_text: 合同文本
            contract_type: 合同类型
            review_focus: 审查焦点

        Returns:
            审查结果字典
        """
        self._ensure_workflow()

        initial_state = ReviewState(
            contract_text=contract_text,
            contract_type=contract_type,
            review_focus=review_focus or [],
            parse_result=None,
            clause_result=None,
            risk_result=None,
            compliance_result=None,
            report_result=None,
            status=ReviewStatus.PENDING.value,
            error=None,
            steps_completed=[]
        )

        result = await self._workflow.ainvoke(initial_state)

        return result

    def get_workflow_info(self) -> Dict[str, Any]:
        """获取工作流信息"""
        return {
            "name": "合同审查工作流",
            "version": "1.0.0",
            "nodes": [
                "parse_document",
                "analyze_clauses",
                "assess_risk",
                "check_compliance",
                "generate_report"
            ],
            "edges": [
                ("parse_document", "analyze_clauses"),
                ("analyze_clauses", "assess_risk"),
                ("assess_risk", "check_compliance"),
                ("check_compliance", "generate_report"),
                ("generate_report", "END")
            ],
            "conditional_edges": [
                ("parse_document", "END (on failure)"),
                ("check_compliance", "END (on severe violation)")
            ]
        }
