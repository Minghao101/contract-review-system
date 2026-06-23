"""
业务事件定义 - Agent间事件驱动协作的标准事件类型

事件链路：
  task.created → DocumentParser
    → document.parsed → RiskAssessor + ClauseAnalyst + ComplianceChecker (并行)
      → risk.analyzed / clause.analyzed / compliance.checked → ReportGenerator
        → task.completed → MultiTurnHandler
"""


class BusinessEvent:
    """标准业务事件常量"""

    # 新任务创建（调度器发布，携带初始合同数据）
    TASK_CREATED = "task.created"

    # 文档解析完成（DocumentParser 发布）
    DOCUMENT_PARSED = "document.parsed"

    # 风险评估完成（RiskAssessmentAgent 发布）
    RISK_ANALYZED = "risk.analyzed"

    # 条款分析完成（ClauseAnalysisAgent 发布）
    CLAUSE_ANALYZED = "clause.analyzed"

    # 合规检查完成（ComplianceCheckerAgent 发布）
    COMPLIANCE_CHECKED = "compliance.checked"

    # 所有分析完成（ReportGenerator 发布）
    TASK_COMPLETED = "task.completed"
