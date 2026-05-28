"""
Skills模块 - 可复用能力模块
"""

from .base_skill import BaseSkill
from .document.pdf_reader import PDFReaderSkill
from .document.docx_parser import DocxParserSkill
from .document.ocr_processor import OCRProcessorSkill
from .legal.clause_parser import ClauseParserSkill
from .legal.regulation_checker import RegulationCheckerSkill
from .legal.case_retriever import CaseRetrieverSkill
from .risk.risk_identifier import RiskIdentifierSkill
from .risk.risk_scorer import RiskScorerSkill
from .risk.mitigation_suggester import MitigationSuggesterSkill
from .report.report_generator import ReportGeneratorSkill
from .report.visualization import VisualizationSkill
from .report.export import ExportSkill
from .skill_registry import SkillRegistry

# 预定义Skills实例
pdf_reader = PDFReaderSkill()
docx_parser = DocxParserSkill()
ocr_processor = OCRProcessorSkill()
clause_parser = ClauseParserSkill()
regulation_checker = RegulationCheckerSkill()
case_retriever = CaseRetrieverSkill()
risk_identifier = RiskIdentifierSkill()
risk_scorer = RiskScorerSkill()
mitigation_suggester = MitigationSuggesterSkill()
report_generator = ReportGeneratorSkill()
visualization = VisualizationSkill()
export = ExportSkill()

# 所有可用Skills
document_skills = [pdf_reader, docx_parser, ocr_processor]
legal_skills = [clause_parser, regulation_checker, case_retriever]
risk_skills = [risk_identifier, risk_scorer, mitigation_suggester]
report_skills = [report_generator, visualization, export]
all_skills = document_skills + legal_skills + risk_skills + report_skills

__all__ = [
    "BaseSkill",
    "PDFReaderSkill",
    "DocxParserSkill",
    "OCRProcessorSkill",
    "ClauseParserSkill",
    "RegulationCheckerSkill",
    "CaseRetrieverSkill",
    "RiskIdentifierSkill",
    "RiskScorerSkill",
    "MitigationSuggesterSkill",
    "ReportGeneratorSkill",
    "VisualizationSkill",
    "ExportSkill",
    "SkillRegistry",
    "pdf_reader",
    "docx_parser",
    "ocr_processor",
    "clause_parser",
    "regulation_checker",
    "case_retriever",
    "risk_identifier",
    "risk_scorer",
    "mitigation_suggester",
    "report_generator",
    "visualization",
    "export",
    "document_skills",
    "legal_skills",
    "risk_skills",
    "report_skills",
    "all_skills",
]
