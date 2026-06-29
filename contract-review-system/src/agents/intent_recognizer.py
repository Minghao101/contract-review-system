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
from enum import Enum
from typing import Any, Dict, List, Optional
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
    MODIFY_CONTRACT = "modify_contract"
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


# ==================== 意图描述（用于Function Calling） ====================

INTENT_DESCRIPTIONS = {
    IntentType.CONTRACT_REVIEW: "完整合同审查。仅当用户明确要求'全面审查'、'完整审查'、'整体分析'时使用。如果用户只要求某个方面（如风险、条款、合规），不要用这个",
    IntentType.CLAUSE_ANALYSIS: "条款分析。当用户询问某个具体条款、要求分析条款内容时使用",
    IntentType.RISK_ASSESSMENT: "风险评估。当用户提到'风险'、要求评估风险、分析风险时使用",
    IntentType.COMPLIANCE_CHECK: "合规检查。当用户提到'合规'、'合法'、要求检查合规性时使用",
    IntentType.REPORT_GENERATION: "报告生成。当用户要求生成、导出、输出报告时使用",
    IntentType.MODIFY_CONTRACT: "修改合同条款。当用户要求修改某个条款的内容，如'把第三条的违约金从5%改成3%'、'删除第X条'、'增加一条...'时使用",
    IntentType.QUESTION_ANSWER: "回答关于合同的问题。当用户提问但不涉及审查/分析/评估时使用",
    IntentType.GREETING: "问候语。当用户打招呼时使用",
    IntentType.UNKNOWN: "无法识别的意图",
}


class IntentRecognizer:
    """
    意图识别器（LLM Function Calling版本）
    """

    def __init__(self, llm=None):
        """
        初始化意图识别器

        Args:
            llm: LLM实例（可选，默认自动创建）
        """
        self.llm = llm or get_llm()
        logger.info("意图识别器初始化: LLM Function Calling模式")

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

        # 始终使用LLM Function Calling识别意图
        return await self._recognize_by_function_calling(text, context)

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
                HumanMessage(content=f"""你是一个意图识别专家。根据用户输入，识别用户意图。

核心规则（按优先级）：
1. 用户打招呼 → greeting
2. 用户追问之前的结果（"之前"、"刚才"、"哪一份"、"第一条"、"第二条"、"什么意思"、"解释一下"、"详细说说"、"为什么"） → question_answer
3. 用户要求修改条款 → modify_contract。关键词包括：
   - "把第X条...改成..."、"删除第X条"、"增加一条..."、"修改..."
   - "加上..."、"添加..."、"加入..."、"补充..."
   - "改成..."、"改为..."、"换成..."、"替换..."
   - "去掉..."、"移除..."
   - 注意：如果用户说"加上XX，再评估风险"，主意图是modify_contract（修改优先于分析）
4. 用户提到"风险"或要求评估风险 → risk_assessment（即使用户说"分析风险"也是risk_assessment，不是contract_review）
5. 用户提到"合规"或要求检查合规 → compliance_check
6. 用户提到"条款"或要求分析条款 → clause_analysis
7. 用户要求生成/导出报告 → report_generation
8. 只有用户明确说"完整审查"、"全面审查"、"整体审查" → contract_review
9. 其他提问 → question_answer
10. 无法判断 → unknown

重要：
- 修改意图优先于分析意图！如果用户同时要求"修改+分析"，识别为modify_contract
- 用户问"这个合同有什么风险"是risk_assessment，不是contract_review！
- 如果对话轮数>0，用户问"第X条建议什么意思"、"解释一下"、"为什么"等，都是question_answer，是在追问之前的结果！

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
            logger.error(f"LLM意图识别失败: {e}")
            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                raw_text=text,
                method="error",
                reasoning=str(e)
            )

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
