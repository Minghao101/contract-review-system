"""
风险管理Skills模块
"""

from .risk_identifier import RiskIdentifierSkill
from .risk_scorer import RiskScorerSkill
from .mitigation_suggester import MitigationSuggesterSkill

# 预定义实例
risk_identifier = RiskIdentifierSkill()
risk_scorer = RiskScorerSkill()
mitigation_suggester = MitigationSuggesterSkill()

# 所有风险管理Skills
risk_skills = [risk_identifier, risk_scorer, mitigation_suggester]

__all__ = [
    "RiskIdentifierSkill",
    "RiskScorerSkill",
    "MitigationSuggesterSkill",
    "risk_identifier",
    "risk_scorer",
    "mitigation_suggester",
    "risk_skills",
]
