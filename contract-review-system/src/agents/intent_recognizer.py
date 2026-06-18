"""
意图识别模块 - 基于Function Calling的LLM意图分类

支持的意图类型：
- CONTRACT_REVIEW: 完整合同审查
- CLAUSE_ANALYSIS: 条款分析
- RISK_ASSESSMENT: 风险评估
- COMPLIANCE_CHECK: 合规检查
- REPORT_GENERATION: 报告生成
- QUESTION_ANSWER: 问题回答
- GREETING: 问候
- UNKNOWN: 未知意图
"""
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import logging

from src.utils.llm_factory import get_llm

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """意图类型枚举"""
    CONTRACT_REVIEW = "contract_review"
    CLAUSE_ANALYSIS = "clause_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    COMPLIANCE_CHECK = "compliance_check"
    REPORT_GENERATION = "report_generation"
    QUESTION_ANSWER = "question_answer"
    GREETING = "greeting"
    UNKNOWN = "unknown"


# ==================== Function Calling 模型 ====================

class IntentResult(BaseModel):
    """意图识别结果（用于Function Calling）"""
    intent: IntentType = Field(
        description="用户意图类型"
    )
    confidence: float = Field(
        description="置信度 0.0-1.0",
        ge=0.0,
        le=1.0
    )
    entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="提取的实体信息"
    )
    reasoning: str = Field(
        default="",
        description="判断理由"
    )


@dataclass
class Intent:
    """意图识别结果"""
    type: IntentType
    confidence: float  # 0.0 - 1.0
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    method: str = "function_calling"  # function_calling / keyword
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "raw_text": self.raw_text[:100],
            "method": self.method,
            "reasoning": self.reasoning
        }


# ==================== 关键词规则（快速路径） ====================

INTENT_KEYWORDS: Dict[IntentType, Dict[str, Any]] = {
    IntentType.CONTRACT_REVIEW: {
        "keywords": [
            "审查合同", "合同审查", "审核合同", "合同审核",
            "检查合同", "合同检查", "分析合同", "合同分析",
            "帮我审查", "帮我分析", "合同文本",
        ],
        "patterns": [
            r"审查.{0,5}合同",
            r"合同.{0,3}审查",
            r"帮我.{0,5}(审查|审核|分析|检查).{0,5}合同",
        ],
        "priority": 10,
    },
    IntentType.CLAUSE_ANALYSIS: {
        "keywords": [
            "条款分析", "分析条款", "解读条款", "条款解读",
        ],
        "patterns": [
            r"(分析|解读|审查).{0,3}条款",
            r"条款.{0,3}(分析|解读|审查)",
        ],
        "priority": 8,
    },
    IntentType.RISK_ASSESSMENT: {
        "keywords": [
            "风险评估", "评估风险", "风险分析", "有什么风险", "风险点",
        ],
        "patterns": [
            r"(评估|分析|检查).{0,10}风险",
            r"有(什么|哪些).{0,5}风险",
        ],
        "priority": 8,
    },
    IntentType.COMPLIANCE_CHECK: {
        "keywords": [
            "合规检查", "是否合法", "是否合规", "合规审查",
        ],
        "patterns": [
            r"是否.{0,3}(合法|合规|符合)",
        ],
        "priority": 7,
    },
    IntentType.REPORT_GENERATION: {
        "keywords": [
            "生成报告", "生成审查报告", "输出报告", "导出报告",
        ],
        "patterns": [
            r"(生成|创建|输出|导出).{0,3}报告",
        ],
        "priority": 6,
    },
    IntentType.QUESTION_ANSWER: {
        "keywords": [
            "什么是", "怎么理解", "什么意思", "请问",
            "之前", "刚才", "上面", "之前解析", "刚才分析",
            "哪一份", "哪个合同", "什么合同",
        ],
        "patterns": [
            r"什么是.{2,}",
            r"什么意思",
            r"之前.{0,5}(解析|分析|审查|处理)",
            r"刚才.{0,5}(解析|分析|审查|处理)",
            r"你.{0,5}(之前|刚才).{0,5}(哪|什么|哪个)",
            r"哪一份合同",
            r"哪个合同",
        ],
        "priority": 5,
    },
    IntentType.GREETING: {
        "keywords": ["你好", "您好", "hello", "hi"],
        "patterns": [r"^(你好|您好|hello|hi)$"],
        "priority": 1,
    },
}


# ==================== 意图描述（用于Function Calling） ====================

INTENT_DESCRIPTIONS = {
    IntentType.CONTRACT_REVIEW: "完整合同审查，包括解析、分析、评估、检查、生成报告。当用户提供合同文本并要求全面审查时使用",
    IntentType.CLAUSE_ANALYSIS: "分析具体条款的内容、含义、风险。当用户询问某个特定条款时使用",
    IntentType.RISK_ASSESSMENT: "评估合同中的风险点、风险等级。当用户关注风险时使用",
    IntentType.COMPLIANCE_CHECK: "检查合同是否符合法律法规、行业标准。当用户关注合规性时使用",
    IntentType.REPORT_GENERATION: "生成合同审查报告。当用户要求生成报告时使用",
    IntentType.QUESTION_ANSWER: "回答关于合同的问题。当用户提问时使用",
    IntentType.GREETING: "问候语。当用户打招呼时使用",
    IntentType.UNKNOWN: "无法识别的意图",
}


class IntentRecognizer:
    """
    意图识别器（Function Calling版本）

    工作流程：
    1. 快速关键词匹配（高置信度直接返回）
    2. 否则调用LLM Function Calling识别
    """

    def __init__(self, llm=None, keyword_threshold: float = 0.7):
        """
        初始化意图识别器

        Args:
            llm: LLM实例（可选，默认自动创建）
            keyword_threshold: 关键词匹配置信度阈值
        """
        self.llm = llm or get_llm()
        self.keyword_threshold = keyword_threshold
        self._keyword_rules = INTENT_KEYWORDS

        logger.info(f"意图识别器初始化: Function Calling模式")

    async def recognize(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        识别用户意图

        Args:
            text: 用户输入文本
            context: 上下文信息（可选）

        Returns:
            Intent: 识别结果
        """
        if not text or not text.strip():
            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                raw_text="",
                method="empty"
            )

        text = text.strip()

        # 1. 快速关键词匹配
        keyword_intent = self._recognize_by_keywords(text, context)
        if keyword_intent.confidence >= self.keyword_threshold:
            logger.debug(f"关键词匹配成功: {keyword_intent.type.value} ({keyword_intent.confidence:.2f})")
            return keyword_intent

        # 2. 调用LLM Function Calling
        return await self._recognize_by_function_calling(text, context)

    def _recognize_by_keywords(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        基于关键词的快速意图识别

        Args:
            text: 用户输入文本
            context: 上下文信息

        Returns:
            Intent: 识别结果
        """
        text_lower = text.lower()
        scores: List[Tuple[IntentType, float, Dict[str, Any]]] = []

        for intent_type, rules in self._keyword_rules.items():
            score, entities = self._score_intent(text, text_lower, rules, context)
            if score > 0:
                scores.append((intent_type, score, entities))

        if not scores:
            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                raw_text=text,
                method="keyword"
            )

        # 按分数排序，取最高分
        scores.sort(key=lambda x: x[1], reverse=True)
        best_intent_type, best_score, entities = scores[0]

        # 归一化置信度到 0-1 范围
        confidence = min(best_score / 10.0, 1.0)

        return Intent(
            type=best_intent_type,
            confidence=confidence,
            entities=entities,
            raw_text=text,
            method="keyword"
        )

    def _score_intent(
        self,
        text: str,
        text_lower: str,
        rules: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """为某个意图打分"""
        score = 0.0
        entities = {}
        priority = rules.get("priority", 1)

        # 关键词匹配
        keywords = rules.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                score += 2.0
                entities["matched_keyword"] = keyword

        # 正则模式匹配（更高权重）
        patterns = rules.get("patterns", [])
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                score += 3.0
                entities["matched_pattern"] = pattern
                if match.groups():
                    entities["extracted"] = match.groups()

        # 上下文加成
        if context:
            last_intent = context.get("last_intent")
            if last_intent and last_intent == rules.get("type", ""):
                score += 1.0

            if context.get("has_contract_text") and score > 0:
                score += 0.5

        # 应用优先级权重
        score *= (priority / 10.0)

        return score, entities

    async def _recognize_by_function_calling(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        基于Function Calling的意图识别

        Args:
            text: 用户输入文本
            context: 上下文信息

        Returns:
            Intent: 识别结果
        """
        try:
            from langchain_core.messages import HumanMessage

            # 构建上下文信息
            context_str = ""
            if context:
                if context.get("last_intent"):
                    context_str += f"\n上一轮意图: {context['last_intent']}"
                if context.get("has_contract_text"):
                    context_str += "\n已有合同文本: 是"
                if context.get("turn_count", 0) > 0:
                    context_str += f"\n对话轮数: {context['turn_count']}（说明之前已有交互）"

            # 构建意图描述
            intent_list = "\n".join([
                f"- {t.value}: {INTENT_DESCRIPTIONS[t]}"
                for t in IntentType if t != IntentType.UNKNOWN
            ])

            # 使用with_structured_output获取结构化输出
            structured_llm = self.llm.with_structured_output(IntentResult)

            messages = [
                HumanMessage(content=f"""你是一个意图识别专家。根据用户输入和上下文，识别用户的意图。

重要规则：
- 如果用户在追问之前分析过什么合同、结果是什么、哪个合同等，应该识别为 question_answer
- 只有当用户明确要求对合同进行审查/分析/评估时，才识别为 contract_review
- 关注"之前"、"刚才"、"哪一份"等表示追问的词汇

可选意图类型：
{intent_list}
{context_str}

用户输入: {text}""")
            ]

            # 调用LLM
            result = await structured_llm.ainvoke(messages)

            return Intent(
                type=result.intent,
                confidence=result.confidence,
                entities=result.entities,
                raw_text=text,
                method="function_calling",
                reasoning=result.reasoning
            )

        except Exception as e:
            logger.warning(f"Function Calling意图识别失败，回退到关键词: {e}")
            # 回退到关键词匹配
            keyword_intent = self._recognize_by_keywords(text, context)
            keyword_intent.confidence = max(keyword_intent.confidence, 0.3)
            return keyword_intent

    def get_supported_intents(self) -> List[Dict[str, str]]:
        """获取支持的意图列表"""
        return [
            {"type": t.value, "description": INTENT_DESCRIPTIONS[t]}
            for t in IntentType
        ]

    async def batch_recognize(self, texts: List[str], context: Optional[Dict[str, Any]] = None) -> List[Intent]:
        """批量意图识别"""
        import asyncio
        tasks = [self.recognize(text, context) for text in texts]
        return await asyncio.gather(*tasks)
