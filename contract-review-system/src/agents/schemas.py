"""
Agent 输出 schema 定义 — 用 Pydantic 模型替代手动 JSON 解析
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ==================== 条款分析 ====================

class CompletenessInfo(BaseModel):
    required_clauses: List[str] = Field(default_factory=list, description="该类型合同必备条款列表")
    found_clauses: List[str] = Field(default_factory=list, description="已找到的必备条款")
    missing_clauses: List[str] = Field(default_factory=list, description="缺失的必备条款")
    completeness_score: float = Field(default=0.0, description="完整性评分 0-1")


class AmbiguousClause(BaseModel):
    issue_type: str = Field(description="问题类型(表述模糊/范围过大/条件不明确/缺乏标准)")
    content: str = Field(description="有问题的原文")
    suggestion: str = Field(description="修改建议")


class RightsObligations(BaseModel):
    rights_count: int = Field(default=0, description="权利数量")
    obligations_count: int = Field(default=0, description="义务数量")
    balance_ratio: float = Field(default=0.5, description="权利义务比")
    balance_assessment: str = Field(default="平衡", description="平衡性判断")
    details: str = Field(default="", description="具体分析")


class AnalysisIssue(BaseModel):
    type: str = Field(description="问题类型")
    severity: str = Field(description="high/medium/low")
    message: str = Field(description="问题描述")
    suggestion: str = Field(description="修改建议")


class AnalysisSummary(BaseModel):
    total_clauses: int = Field(default=0, description="条款总数")
    total_issues: int = Field(default=0, description="问题总数")
    overall_assessment: str = Field(default="", description="整体评估")
    key_recommendations: List[str] = Field(default_factory=list, description="关键建议")


class ClauseAnalysisResult(BaseModel):
    contract_type: str = Field(default="general", description="合同类型")
    completeness: CompletenessInfo = Field(default_factory=CompletenessInfo)
    ambiguous_clauses: List[AmbiguousClause] = Field(default_factory=list)
    key_clauses: Dict[str, str] = Field(default_factory=dict, description="关键条款摘要")
    rights_obligations: RightsObligations = Field(default_factory=RightsObligations)
    issues: List[AnalysisIssue] = Field(default_factory=list)
    summary: AnalysisSummary = Field(default_factory=AnalysisSummary)


# ==================== 合规检查 ====================

class CheckedRegulation(BaseModel):
    regulation: str = Field(description="法规/标准名称")
    status: str = Field(description="compliant/violation/missing")
    details: str = Field(description="具体说明")


class ComplianceViolation(BaseModel):
    clause: str = Field(description="有问题的条款内容")
    regulation: str = Field(description="违反的法规或标准")
    severity: str = Field(description="high/medium/low")
    suggestion: str = Field(description="修改建议")


class ComplianceSummary(BaseModel):
    total_checked: int = Field(default=0, description="检查项总数")
    compliant_count: int = Field(default=0, description="合规数量")
    violation_count: int = Field(default=0, description="违规数量")
    missing_count: int = Field(default=0, description="缺失数量")
    assessment: str = Field(default="", description="整体合规评估")


class ComplianceCheckResult(BaseModel):
    compliance_status: str = Field(description="compliant/partial/non_compliant")
    checked_regulations: List[CheckedRegulation] = Field(default_factory=list)
    missing_clauses: List[str] = Field(default_factory=list)
    compliance_violations: List[ComplianceViolation] = Field(default_factory=list)
    score: int = Field(default=0, description="合规评分 0-100")
    summary: ComplianceSummary = Field(default_factory=ComplianceSummary)


# ==================== 风险评估 ====================

class RiskItem(BaseModel):
    name: str = Field(description="风险名称")
    severity: str = Field(description="high/medium/low")
    category: str = Field(description="liability/termination/payment/ip/confidentiality/dispute/other")
    description: str = Field(description="风险详细描述")
    impact: str = Field(description="可能的影响")
    suggestion: str = Field(description="具体的修改建议")


class RiskRecommendation(BaseModel):
    priority: str = Field(description="high/medium/low")
    category: str = Field(description="类别")
    suggestion: str = Field(description="具体建议")
    reason: str = Field(description="建议原因")


class RiskSummary(BaseModel):
    total_risks: int = Field(default=0, description="风险总数")
    high_risks: int = Field(default=0, description="高风险数")
    medium_risks: int = Field(default=0, description="中风险数")
    low_risks: int = Field(default=0, description="低风险数")
    overall_assessment: str = Field(default="", description="整体风险评估")
    key_concerns: List[str] = Field(default_factory=list, description="主要关注点")


class RiskAssessmentResult(BaseModel):
    risk_level: str = Field(description="low/medium/high/critical")
    risks: List[RiskItem] = Field(default_factory=list)
    recommendations: List[RiskRecommendation] = Field(default_factory=list)
    summary: RiskSummary = Field(default_factory=RiskSummary)


# ==================== 报告生成 ====================

class DocumentOverview(BaseModel):
    contract_type: str = Field(default="", description="合同类型")
    parties: List[str] = Field(default_factory=list, description="签约方")
    key_terms: str = Field(default="", description="核心条款概述")


class CompletenessAnalysis(BaseModel):
    score: float = Field(default=0.0, description="完整性评分")
    found: List[str] = Field(default_factory=list, description="已找到的条款")
    missing: List[str] = Field(default_factory=list, description="缺失的条款")
    assessment: str = Field(default="", description="完整性评估")


class ReportRiskAssessment(BaseModel):
    overall_level: str = Field(default="", description="风险等级")
    high_risks: List[str] = Field(default_factory=list, description="高风险项")
    medium_risks: List[str] = Field(default_factory=list, description="中风险项")
    low_risks: List[str] = Field(default_factory=list, description="低风险项")


class ReportRecommendation(BaseModel):
    priority: str = Field(description="high/medium/low")
    category: str = Field(description="类别")
    content: str = Field(description="具体建议")


class Conclusion(BaseModel):
    verdict: str = Field(description="建议签署/建议修改后签署/不建议签署")
    reason: str = Field(description="结论原因")
    next_steps: List[str] = Field(default_factory=list, description="后续步骤")


class ReportBody(BaseModel):
    title: str = Field(default="合同审查报告", description="报告标题")
    executive_summary: str = Field(default="", description="执行摘要")
    document_overview: DocumentOverview = Field(default_factory=DocumentOverview)
    completeness_analysis: CompletenessAnalysis = Field(default_factory=CompletenessAnalysis)
    risk_assessment: ReportRiskAssessment = Field(default_factory=ReportRiskAssessment)
    recommendations: List[ReportRecommendation] = Field(default_factory=list)
    conclusion: Conclusion = Field(default_factory=Conclusion)


class ReportSummary(BaseModel):
    risk_level: str = Field(default="unknown", description="风险等级")
    completeness_score: float = Field(default=0.0, description="完整性评分")
    total_issues: int = Field(default=0, description="问题总数")
    verdict: str = Field(default="", description="最终结论")


class Visualization(BaseModel):
    risk_distribution: Dict[str, int] = Field(default_factory=dict, description="风险分布")
    completeness_bar: int = Field(default=0, description="完整性百分比")


class ReportResult(BaseModel):
    report: ReportBody = Field(default_factory=ReportBody)
    summary: ReportSummary = Field(default_factory=ReportSummary)
    visualization: Visualization = Field(default_factory=Visualization)


# ==================== 文档解析 ====================

class BasicInfo(BaseModel):
    title: str = Field(default="", description="合同标题")
    contract_number: Optional[str] = Field(default=None, description="合同编号")
    signing_place: Optional[str] = Field(default=None, description="签订地点")
    parties: List[str] = Field(default_factory=list, description="签约方")
    signing_date: Optional[str] = Field(default=None, description="签署日期")


class Section(BaseModel):
    id: str = Field(description="条款编号")
    title: str = Field(default="", description="条款标题")
    content: str = Field(description="条款完整内容")
    level: int = Field(default=1, description="层级")


class DateInfo(BaseModel):
    raw: str = Field(description="原始文本")
    date: str = Field(description="YYYY-MM-DD")
    type: str = Field(description="签署/生效/到期/交付/付款/其他")


class AmountInfo(BaseModel):
    raw: str = Field(description="原始文本")
    value: float = Field(description="数值（元）")
    currency: str = Field(default="CNY", description="货币")
    type: str = Field(description="总价/单价/付款/违约金/其他")


class Definition(BaseModel):
    term: str = Field(description="术语")
    definition: str = Field(description="定义内容")


class DocumentExtractionResult(BaseModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    contract_type: str = Field(default="general", description="合同类型")
    sections: List[Section] = Field(default_factory=list)
    dates: List[DateInfo] = Field(default_factory=list)
    amounts: List[AmountInfo] = Field(default_factory=list)
    definitions: List[Definition] = Field(default_factory=list)

    @field_validator("dates", mode="before")
    @classmethod
    def normalize_dates(cls, v):
        """允许 LLM 返回简单字符串日期，自动转换为 DateInfo"""
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(DateInfo(raw=item, date=item, type="其他"))
            elif isinstance(item, dict):
                result.append(DateInfo(**item))
            else:
                result.append(item)
        return result

    @field_validator("amounts", mode="before")
    @classmethod
    def normalize_amounts(cls, v):
        """允许 LLM 返回简单数值金额，自动转换为 AmountInfo"""
        result = []
        for item in v:
            if isinstance(item, (int, float)):
                result.append(AmountInfo(raw=str(item), value=float(item), type="其他"))
            elif isinstance(item, str):
                try:
                    val = float(item)
                    result.append(AmountInfo(raw=item, value=val, type="其他"))
                except ValueError:
                    pass
            elif isinstance(item, dict):
                result.append(AmountInfo(**item))
            else:
                result.append(item)
        return result


# ==================== 条款定位 ====================

class ClauseLocation(BaseModel):
    clause_id: str = Field(description="条款编号")
    confidence: float = Field(default=0.5, description="置信度")


# ==================== 新增条款 ====================

class NewClause(BaseModel):
    id: str = Field(description="新条款编号")
    title: str = Field(description="条款标题")
    content: str = Field(description="条款完整内容")
    level: int = Field(default=1, description="层级")


class InsertClauseResult(BaseModel):
    insert_after_clause_id: str = Field(description="目标条款编号")
    new_clause: NewClause = Field(description="新条款")
    confidence: float = Field(default=0.8, description="置信度")


# ==================== 修改指令 ====================

class ModifyInstructionResult(BaseModel):
    action: str = Field(description="replace/delete/insert")
    locate_type: str = Field(description="clause_number/clause_title/semantic")
    locate_value: str = Field(description="定位值")
    old_content: str = Field(default="", description="被替换的原文")
    new_content: str = Field(default="", description="新内容")
    target_scope: str = Field(default="single_clause", description="作用范围")
    confidence: float = Field(default=0.8, description="置信度")
