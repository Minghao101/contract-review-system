"""
报告生成Skills模块
"""

from .report_generator import ReportGeneratorSkill
from .visualization import VisualizationSkill
from .export import ExportSkill

# 预定义实例
report_generator = ReportGeneratorSkill()
visualization = VisualizationSkill()
export = ExportSkill()

# 所有报告生成Skills
report_skills = [report_generator, visualization, export]

__all__ = [
    "ReportGeneratorSkill",
    "VisualizationSkill",
    "ExportSkill",
    "report_generator",
    "visualization",
    "export",
    "report_skills",
]
