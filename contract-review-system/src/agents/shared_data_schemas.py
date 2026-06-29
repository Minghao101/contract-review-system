"""
共享数据 Schema 定义

所有 Agent 间通过共享内存传递的数据都有明确的 Pydantic Schema，
杜绝魔法字符串和运行时取值错误。
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentParseResult(BaseModel):
    """文档解析结果（DocumentParser → SharedMemory ANALYSIS 层）"""
    document_info: Dict[str, Any] = Field(default_factory=dict, description="文档基本信息")
    sections: List[Dict[str, Any]] = Field(default_factory=list, description="条款列表")
    dates: List[Dict[str, Any]] = Field(default_factory=list, description="日期信息")
    amounts: List[Dict[str, Any]] = Field(default_factory=list, description="金额信息")
    parties: List[str] = Field(default_factory=list, description="当事方")
    definitions: List[Dict[str, Any]] = Field(default_factory=list, description="术语定义")


class RiskAssessmentResult(BaseModel):
    """风险评估结果（RiskAssessor → SharedMemory ANALYSIS 层）"""
    risk_level: str = Field(default="unknown", description="风险等级: low/medium/high/critical")
    risks: List[Dict[str, Any]] = Field(default_factory=list, description="风险列表")
    recommendations: List[Dict[str, Any]] = Field(default_factory=list, description="建议列表")
    summary: Dict[str, Any] = Field(default_factory=dict, description="摘要")
    risk_quantification: Dict[str, Any] = Field(default_factory=dict, description="量化评分")
    mitigation_plan: List[Dict[str, Any]] = Field(default_factory=list, description="缓解计划")


class ClauseAnalysisResult(BaseModel):
    """条款分析结果（ClauseAnalyst → SharedMemory ANALYSIS 层）"""
    sections: Dict[str, Any] = Field(default_factory=dict, description="关键条款摘要")
    analysis: Dict[str, Any] = Field(default_factory=dict, description="分析详情")
    missing_clauses: List[str] = Field(default_factory=list, description="缺失条款")
    issues_found: int = Field(default=0, description="问题数量")
    issues: List[Dict[str, Any]] = Field(default_factory=list, description="问题列表")


class ComplianceCheckResult(BaseModel):
    """合规检查结果（ComplianceChecker → SharedMemory ANALYSIS 层）"""
    compliance_status: str = Field(default="unknown", description="合规状态")
    checked_regulations: List[Dict[str, Any]] = Field(default_factory=list, description="已检查法规")
    missing_clauses: List[str] = Field(default_factory=list, description="缺失必备条款")
    compliance_violations: List[Dict[str, Any]] = Field(default_factory=list, description="违规项")
    score: int = Field(default=0, description="合规评分")
    summary: Dict[str, Any] = Field(default_factory=dict, description="摘要")


class ReportResult(BaseModel):
    """报告生成结果（ReportGenerator → SharedMemory DECISION 层）"""
    report: Dict[str, Any] = Field(default_factory=dict, description="报告内容")
    summary: Dict[str, Any] = Field(default_factory=dict, description="摘要")
    visualization: Dict[str, Any] = Field(default_factory=dict, description="可视化数据")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="生成时间")


class ModifyInstruction(BaseModel):
    """增量修改指令（LLM 解析用户意图后生成）"""
    action: str = Field(description="修改动作: replace/delete/insert")
    locate_type: str = Field(description="定位方式: clause_number/clause_title/semantic")
    locate_value: str = Field(description="定位值: '第三条'/'违约责任'/'关于付款的条款'")
    old_content: Optional[str] = Field(default=None, description="被替换的原文片段（replace 时必填）")
    new_content: Optional[str] = Field(default=None, description="新内容（replace/insert 时必填）")
    target_scope: str = Field(default="single_clause", description="影响范围: single_clause/multiple_clauses/full_document")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="定位置信度")


# 共享内存 Schema 注册表：key → Schema 类（key 与 agent_id 一致）
SHARED_DATA_SCHEMAS: Dict[str, type] = {
    "document_parser": DocumentParseResult,
    "risk_assessor": RiskAssessmentResult,
    "clause_analyst": ClauseAnalysisResult,
    "compliance_checker": ComplianceCheckResult,
    "report_generator": ReportResult,
    "modify_instruction": ModifyInstruction,
}


def validate_shared_data(key: str, value: Any) -> bool:
    """
    校验共享数据是否符合 Schema

    Args:
        key: 共享内存键名
        value: 待写入的值

    Returns:
        是否通过校验
    """
    schema_class = SHARED_DATA_SCHEMAS.get(key)
    if schema_class is None:
        return True  # 非核心数据不校验

    try:
        if isinstance(value, dict):
            schema_class(**value)
        elif isinstance(value, BaseModel):
            schema_class(**value.model_dump())
        else:
            return False
        return True
    except Exception:
        return False
