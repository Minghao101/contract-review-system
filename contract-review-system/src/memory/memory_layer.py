"""
记忆层次模块 - 定义共享记忆的层次结构
"""
from enum import Enum


class MemoryLayer(Enum):
    """
    记忆层次枚举

    共享记忆分为三层：
    - CONTEXT: 合同上下文（原始文档、结构化条款、元数据）
    - ANALYSIS: 分析结果（条款分析、风险评估、合规检查）
    - DECISION: 决策历史（审查决策、冲突解决、最终建议）
    """
    CONTEXT = "context"      # 合同上下文
    ANALYSIS = "analysis"    # 分析结果
    DECISION = "decision"    # 决策历史

    def __str__(self):
        return self.value
