"""
法规检查Skill - LLM驱动 + Qdrant向量检索，检查合同合规性
"""
from typing import Any, Dict, List, Optional
import logging

from ..base_skill import BaseSkill
from config.settings import settings
from src.utils.llm_factory import get_llm
from src.utils.llm_response import parse_json_from_llm

logger = logging.getLogger(__name__)


class RegulationCheckerSkill(BaseSkill):
    """
    法规检查Skill（LLM驱动版）

    功能：
    - 使用LLM检查合同条款是否符合相关法律法规
    - 识别违规条款
    - 提供法规引用和修改建议
    - 向量检索相关法规（语义匹配）
    """

    def __init__(self):
        super().__init__(
            skill_id="regulation_checker",
            name="法规检查",
            description="检查合同条款是否符合相关法律法规，识别违规条款",
        )
        self._vector_store = None

    @property
    def vector_store(self):
        """延迟加载向量存储"""
        if self._vector_store is None:
            try:
                from src.services.vector_store import get_vector_store
                self._vector_store = get_vector_store()
            except Exception as e:
                logger.warning(f"Qdrant连接失败，跳过向量检索: {e}")
                self._vector_store = False
        return self._vector_store

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行法规检查

        Args:
            **kwargs:
                - text: 合同文本（必填）
                - contract_type: 合同类型（可选）
                - regulations: 自定义法规规则（可选，忽略）

        Returns:
            法规检查结果
        """
        text = kwargs.get("text", "")
        contract_type = kwargs.get("contract_type", "general")

        if not text:
            return {"error": "请提供合同文本"}

        try:
            violations = await self._check_with_llm(text, contract_type)
            related_regulations = self._vector_search_regulations(text)

            high_count = len([v for v in violations if v.get("severity") == "high"])
            medium_count = len([v for v in violations if v.get("severity") == "medium"])
            low_count = len([v for v in violations if v.get("severity") == "low"])

            return {
                "total_rules_checked": len(violations),
                "violations_found": len(violations),
                "violations": violations,
                "related_regulations": related_regulations,
                "missing_clauses": [],
                "compliance_score": max(0, 100 - high_count * 20 - medium_count * 10 - low_count * 5),
                "summary": {
                    "high_severity": high_count,
                    "medium_severity": medium_count,
                    "low_severity": low_count,
                },
            }
        except Exception as e:
            logger.error(f"法规检查失败: {e}")
            return {"error": str(e)}

    async def _check_with_llm(self, text: str, contract_type: str) -> List[Dict[str, Any]]:
        """使用LLM检查法规合规性"""
        llm = get_llm()

        system_prompt = f"""你是一个合同法规合规审查专家。当前合同类型: {contract_type}

请检查合同是否存在以下法规违规问题：
1. 免责条款违规（《民法典》第506条）
2. 违约金过高（《民法典》第585条）
3. 仲裁诉讼并存（《仲裁法》第5条）
4. 工作时间违规（《劳动法》第36条）
5. 加班费免除（《劳动法》第44条）
6. 格式条款违规（《消费者权益保护法》）
7. 个人信息保护违规（《个人信息保护法》）
8. 知识产权归属问题（《著作权法》/《专利法》）

输出格式要求（必须是严格有效的JSON数组）：
[
  {{
    "regulation": "违反的法规名称",
    "category": "免责条款/违约金/争议解决/工作时间/加班/格式条款/数据保护/知识产权",
    "severity": "high/medium/low",
    "description": "违规描述",
    "suggestion": "修改建议"
  }}
]

如果合同没有发现法规违规问题，返回空数组 []
只输出JSON数组，不要其他内容"""

        user_message = f"请检查以下合同的法规合规性：\n\n{text[:8000]}"

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)

            result = parse_json_from_llm(content)
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"LLM法规检查失败: {e}")
            return []

    def _vector_search_regulations(self, text: str) -> List[Dict[str, Any]]:
        """向量检索与合同文本相关的法规"""
        if not self.vector_store or self.vector_store is False:
            return []

        try:
            query = text[:2000]
            results = self.vector_store.search(
                collection_name=settings.QDRANT_COLLECTION_REGULATIONS,
                query=query,
                top_k=5,
            )
            return results
        except Exception as e:
            logger.warning(f"法规向量检索失败: {e}")
            return []
