"""
意图识别模块 - 基于关键词和LLM的意图分类

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
import logging

from src.utils.llm_response import extract_llm_content, parse_json_from_llm

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


@dataclass
class Intent:
    """意图识别结果"""
    type: IntentType
    confidence: float  # 0.0 - 1.0
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    method: str = "keyword"  # keyword / llm / hybrid

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "raw_text": self.raw_text[:100],
            "method": self.method
        }


# ==================== 关键词规则 ====================

INTENT_KEYWORDS: Dict[IntentType, Dict[str, Any]] = {
    IntentType.CONTRACT_REVIEW: {
        "keywords": [
            "审查合同", "合同审查", "审核合同", "合同审核",
            "检查合同", "合同检查", "分析合同", "合同分析",
            "看看这个合同", "帮我看看", "帮我审查", "帮我分析",
            "这份合同", "这个合同", "该合同", "合同文本",
            "review", "contract review", "analyze contract",
        ],
        "patterns": [
            r"审查.{0,5}合同",
            r"合同.{0,3}审查",
            r"审核.{0,5}合同",
            r"分析.{0,5}合同",
            r"检查.{0,5}合同",
            r"帮我.{0,5}(审查|审核|分析|检查).{0,5}合同",
            r"合同.{0,5}(条款|问题|内容)",
        ],
        "min_text_length": 50,  # 合同文本通常较长
        "priority": 10,
    },
    IntentType.CLAUSE_ANALYSIS: {
        "keywords": [
            "条款分析", "分析条款", "解读条款", "条款解读",
            "条款审查", "审查条款", "条款内容", "具体条款",
            "clause", "clause analysis",
        ],
        "patterns": [
            r"(分析|解读|审查|检查).{0,3}条款",
            r"条款.{0,3}(分析|解读|审查|检查)",
            r"第.{1,5}(条|款).{0,10}(分析|解读|意思|含义)",
        ],
        "priority": 8,
    },
    IntentType.RISK_ASSESSMENT: {
        "keywords": [
            "风险评估", "评估风险", "风险分析", "分析风险",
            "风险检查", "检查风险", "有什么风险", "风险点",
            "潜在风险", "风险提示", "风险等级", "风险",
            "risk", "risk assessment", "risk analysis",
        ],
        "patterns": [
            r"(评估|分析|检查|识别).{0,10}风险",
            r"风险.{0,5}(评估|分析|检查|识别)",
            r"有(什么|哪些).{0,5}风险",
            r"存在.{0,5}风险",
            r"(看看|查看|了解).{0,5}风险",
        ],
        "priority": 8,
    },
    IntentType.COMPLIANCE_CHECK: {
        "keywords": [
            "合规检查", "检查合规", "合规性", "合法合规",
            "法律法规", "是否合法", "是否合规", "合规审查",
            "compliance", "compliance check",
        ],
        "patterns": [
            r"(检查|审查|评估).{0,3}合规",
            r"合规.{0,3}(检查|审查|评估)",
            r"是否.{0,3}(合法|合规|符合)",
            r"符合.{0,3}(法律|法规|规定)",
        ],
        "priority": 7,
    },
    IntentType.REPORT_GENERATION: {
        "keywords": [
            "生成报告", "生成审查报告", "报告生成", "输出报告",
            "导出报告", "审查报告", "总结报告", "综合报告",
            "generate report", "create report",
        ],
        "patterns": [
            r"(生成|创建|输出|导出).{0,3}报告",
            r"报告.{0,3}(生成|创建|输出|导出)",
            r"给我.{0,3}报告",
        ],
        "priority": 6,
    },
    IntentType.QUESTION_ANSWER: {
        "keywords": [
            "什么是", "怎么理解", "什么意思", "如何解释",
            "请问", "问一下", "咨询", "疑问",
            "question", "what is", "how to",
        ],
        "patterns": [
            r"什么是.{2,}",
            r"怎么.{0,3}理解",
            r"什么意思",
            r"(请问|问一下).{2,}",
        ],
        "priority": 4,
    },
    IntentType.GREETING: {
        "keywords": [
            "你好", "您好", "hello", "hi", "嗨",
            "早上好", "下午好", "晚上好",
        ],
        "patterns": [
            r"^(你好|您好|hello|hi|嗨)$",
            r"^(早上好|下午好|晚上好)",
        ],
        "priority": 1,
    },
}


class IntentRecognizer:
    """
    意图识别器

    支持三种模式：
    1. keyword: 基于关键词和正则表达式匹配
    2. llm: 基于LLM的语义理解（需要LLM实例）
    3. hybrid: 先关键词匹配，低置信度时回退到LLM
    """

    def __init__(self, llm=None, mode: str = "keyword"):
        """
        初始化意图识别器

        Args:
            llm: LLM实例（可选，用于hybrid/llm模式）
            mode: 识别模式 (keyword/llm/hybrid)
        """
        self.llm = llm
        self.mode = mode
        self._keyword_rules = INTENT_KEYWORDS

        logger.info(f"意图识别器初始化: mode={mode}")

    def recognize(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
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

        if self.mode == "keyword":
            return self._recognize_by_keywords(text, context)
        elif self.mode == "llm":
            return self._recognize_by_llm(text, context)
        elif self.mode == "hybrid":
            keyword_intent = self._recognize_by_keywords(text, context)
            if keyword_intent.confidence >= 0.6:
                return keyword_intent
            # 低置信度时尝试LLM
            if self.llm:
                llm_intent = self._recognize_by_llm(text, context)
                if llm_intent.confidence > keyword_intent.confidence:
                    return llm_intent
            return keyword_intent
        else:
            return self._recognize_by_keywords(text, context)

    def _recognize_by_keywords(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        基于关键词的意图识别

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

        # 如果是合同审查意图，检查文本长度
        if best_intent_type == IntentType.CONTRACT_REVIEW:
            min_length = self._keyword_rules[IntentType.CONTRACT_REVIEW].get("min_text_length", 0)
            if min_length > 0 and len(text) < min_length:
                # 文本太短，降低置信度（但不降级意图类型，因为用户可能只是简短描述）
                confidence *= 0.6

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
        """
        为某个意图打分

        Returns:
            (score, entities): 分数和提取的实体
        """
        score = 0.0
        entities = {}
        priority = rules.get("priority", 1)

        # 1. 关键词匹配
        keywords = rules.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                score += 2.0
                entities["matched_keyword"] = keyword

        # 2. 正则模式匹配（更高权重）
        patterns = rules.get("patterns", [])
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                score += 3.0
                entities["matched_pattern"] = pattern
                # 提取捕获组作为实体
                if match.groups():
                    entities["extracted"] = match.groups()

        # 3. 上下文加成
        if context:
            last_intent = context.get("last_intent")
            if last_intent and last_intent == rules.get("type", ""):
                score += 1.0  # 连续意图加成

            # 如果上下文中有合同文本，合同审查意图加分
            if context.get("has_contract_text") and score > 0:
                score += 0.5

        # 4. 应用优先级权重
        score *= (priority / 10.0)

        return score, entities

    def _recognize_by_llm(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """
        基于LLM的意图识别

        Args:
            text: 用户输入文本
            context: 上下文信息

        Returns:
            Intent: 识别结果
        """
        if not self.llm:
            logger.warning("LLM未初始化，回退到关键词识别")
            return self._recognize_by_keywords(text, context)

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            intent_descriptions = "\n".join([
                f"- {t.value}: {self._get_intent_description(t)}"
                for t in IntentType
            ])

            system_prompt = f"""你是一个意图识别专家。根据用户输入，识别用户的意图。

可选意图类型：
{intent_descriptions}

输出格式（JSON）：
{{
    "intent": "意图类型",
    "confidence": 0.0-1.0,
    "entities": {{}}
}}

只输出JSON，不要其他内容。"""

            context_str = ""
            if context:
                if context.get("last_intent"):
                    context_str += f"\n上一轮意图: {context['last_intent']}"
                if context.get("has_contract_text"):
                    context_str += "\n已有合同文本: 是"

            human_prompt = f"用户输入: {text}{context_str}\n\n请识别意图。"

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]

            response = self.llm.invoke(messages)
            content = extract_llm_content(response.content)

            # 尝试解析JSON
            result = parse_json_from_llm(content)

            # 如果解析结果不是dict，使用默认值
            if not isinstance(result, dict):
                result = {"intent": "unknown", "confidence": 0.5}

            intent_type_str = result.get("intent", "unknown")
            try:
                intent_type = IntentType(intent_type_str)
            except ValueError:
                intent_type = IntentType.UNKNOWN

            return Intent(
                type=intent_type,
                confidence=float(result.get("confidence", 0.5)),
                entities=result.get("entities", {}),
                raw_text=text,
                method="llm"
            )

        except Exception as e:
            logger.warning(f"LLM意图识别失败，回退到关键词: {e}")
            return self._recognize_by_keywords(text, context)

    def _get_intent_description(self, intent_type: IntentType) -> str:
        """获取意图类型的描述"""
        descriptions = {
            IntentType.CONTRACT_REVIEW: "完整合同审查（解析、分析、评估、检查、报告）",
            IntentType.CLAUSE_ANALYSIS: "分析具体条款的内容和含义",
            IntentType.RISK_ASSESSMENT: "评估合同中的风险点",
            IntentType.COMPLIANCE_CHECK: "检查合同是否符合法律法规",
            IntentType.REPORT_GENERATION: "生成审查报告",
            IntentType.QUESTION_ANSWER: "回答关于合同的问题",
            IntentType.GREETING: "问候语",
            IntentType.UNKNOWN: "无法识别的意图",
        }
        return descriptions.get(intent_type, "未知意图")

    def get_supported_intents(self) -> List[Dict[str, str]]:
        """获取支持的意图列表"""
        return [
            {"type": t.value, "description": self._get_intent_description(t)}
            for t in IntentType
        ]

    def add_keyword_rule(
        self,
        intent_type: IntentType,
        keywords: List[str] = None,
        patterns: List[str] = None,
        priority: int = 5
    ):
        """
        添加自定义关键词规则

        Args:
            intent_type: 意图类型
            keywords: 关键词列表
            patterns: 正则模式列表
            priority: 优先级
        """
        if intent_type not in self._keyword_rules:
            self._keyword_rules[intent_type] = {
                "keywords": [],
                "patterns": [],
                "priority": priority
            }

        if keywords:
            self._keyword_rules[intent_type]["keywords"].extend(keywords)
        if patterns:
            self._keyword_rules[intent_type]["patterns"].extend(patterns)

        logger.info(f"添加关键词规则: {intent_type.value}")

    def batch_recognize(self, texts: List[str], context: Optional[Dict[str, Any]] = None) -> List[Intent]:
        """
        批量意图识别

        Args:
            texts: 文本列表
            context: 上下文信息

        Returns:
            意图列表
        """
        return [self.recognize(text, context) for text in texts]
