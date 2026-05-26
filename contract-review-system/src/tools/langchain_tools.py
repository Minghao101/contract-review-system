"""
LangChain工具模块 - 定义合同审查相关的工具
"""
from typing import Optional
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.llm_factory import get_llm


@tool
def analyze_clause(clause_text: str, clause_type: str = "general") -> str:
    """
    使用LLM分析单个合同条款

    Args:
        clause_text: 条款文本
        clause_type: 条款类型 (general/payment/delivery/liability/dispute)

    Returns:
        条款分析结果
    """
    llm = get_llm()

    system_prompt = """你是一个专业的合同法律分析师。请分析以下合同条款，给出：
1. 条款的主要内容概述
2. 条款的合理性评估
3. 潜在的风险点
4. 改进建议

请用中文回答，格式清晰。"""

    human_prompt = f"""请分析以下{clause_type}类型的合同条款：

{clause_text}

请提供详细的分析报告。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]

    response = llm.invoke(messages)
    return response.content


@tool
def assess_risk(contract_text: str, focus_areas: str = "") -> str:
    """
    使用LLM评估合同整体风险

    Args:
        contract_text: 合同文本
        focus_areas: 关注领域 (可选，逗号分隔)

    Returns:
        风险评估结果
    """
    llm = get_llm()

    focus_instruction = ""
    if focus_areas:
        focus_instruction = f"\n特别关注以下领域：{focus_areas}"

    system_prompt = """你是一个资深的合同风险评估专家。请对以下合同进行全面的风险评估，包括：
1. 整体风险等级 (低/中/高/极高)
2. 主要风险点列举
3. 每个风险点的严重程度和影响
4. 具体的改进建议

请用中文回答，格式清晰。"""

    human_prompt = f"""请对以下合同进行风险评估：{focus_instruction}

合同内容：
{contract_text}

请提供详细的风险评估报告。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]

    response = llm.invoke(messages)
    return response.content


@tool
def generate_suggestions(contract_text: str, issues: str) -> str:
    """
    使用LLM生成合同修改建议

    Args:
        contract_text: 合同文本
        issues: 发现的问题 (逗号分隔)

    Returns:
        修改建议
    """
    llm = get_llm()

    system_prompt = """你是一个专业的合同法律顾问。根据发现的问题，请提供具体的合同修改建议，包括：
1. 针对每个问题的具体修改方案
2. 建议的条款措辞
3. 修改的优先级
4. 注意事项

请用中文回答，格式清晰。"""

    human_prompt = f"""合同发现以下问题：
{issues}

请提供具体的修改建议。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]

    response = llm.invoke(messages)
    return response.content


@tool
def summarize_contract(contract_text: str) -> str:
    """
    使用LLM生成合同摘要

    Args:
        contract_text: 合同文本

    Returns:
        合同摘要
    """
    llm = get_llm()

    system_prompt = """你是一个专业的合同分析师。请为以下合同生成一份简洁的摘要，包括：
1. 合同类型和目的
2. 主要当事人
3. 核心条款概述
4. 关键金额和期限
5. 重要注意事项

请用中文回答，格式清晰。"""

    human_prompt = f"""请为以下合同生成摘要：

{contract_text}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]

    response = llm.invoke(messages)
    return response.content


# 工具列表
contract_tools = [
    analyze_clause,
    assess_risk,
    generate_suggestions,
    summarize_contract,
]
