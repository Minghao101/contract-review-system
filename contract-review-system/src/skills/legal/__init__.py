"""
法律分析Skills模块
"""

from .clause_parser import ClauseParserSkill
from .regulation_checker import RegulationCheckerSkill
from .case_retriever import CaseRetrieverSkill

# 预定义实例
clause_parser = ClauseParserSkill()
regulation_checker = RegulationCheckerSkill()
case_retriever = CaseRetrieverSkill()

# 所有法律分析Skills
legal_skills = [clause_parser, regulation_checker, case_retriever]

__all__ = [
    "ClauseParserSkill",
    "RegulationCheckerSkill",
    "CaseRetrieverSkill",
    "clause_parser",
    "regulation_checker",
    "case_retriever",
    "legal_skills",
]
