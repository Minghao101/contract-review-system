"""
Agent模块 - 包含所有Agent实现

LangChain 高级抽象：
- schemas: Pydantic 输出模型（替代手动 JSON 解析）
- BaseAgent.chat_structured(): 使用 with_structured_output() 返回结构化结果
- 各 Agent 使用 ChatPromptTemplate 构建 prompt
"""

from .base_agent import BaseAgent
from .business_events import BusinessEvent
from .communication import AgentMessage, MessageType, MessageBus, message_bus
from .coordinator_agent import CoordinatorAgent
from .document_parser_agent import DocumentParserAgent
from .clause_analysis_agent import ClauseAnalysisAgent
from .risk_assessment_agent import RiskAssessmentAgent
from .compliance_checker_agent import ComplianceCheckerAgent
from .report_generator_agent import ReportGeneratorAgent
from .langchain_agent import LangChainAgentWrapper, create_llm_agent
from .agent_tools import AgentTools, AgentWithTools
from .intent_recognizer import IntentRecognizer, IntentType, Intent
from .conversation_context import (
    ConversationContext, ConversationManager, ConversationState,
    Message, TurnContext
)
from .multi_turn_handler import MultiTurnHandler
from . import schemas

__all__ = [
    "BaseAgent",
    "BusinessEvent",
    "AgentMessage",
    "MessageType",
    "MessageBus",
    "message_bus",
    "CoordinatorAgent",
    "DocumentParserAgent",
    "ClauseAnalysisAgent",
    "RiskAssessmentAgent",
    "ComplianceCheckerAgent",
    "ReportGeneratorAgent",
    "LangChainAgentWrapper",
    "create_llm_agent",
    "AgentTools",
    "AgentWithTools",
    "IntentRecognizer",
    "IntentType",
    "Intent",
    "ConversationContext",
    "ConversationManager",
    "ConversationState",
    "Message",
    "TurnContext",
    "MultiTurnHandler",
    "schemas",
]
