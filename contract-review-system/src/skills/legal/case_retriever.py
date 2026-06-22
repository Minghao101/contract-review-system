"""
案例检索Skill - LLM驱动 + Qdrant向量检索相关法律案例和判例
"""
from typing import Any, Dict, List, Optional
import logging

from ..base_skill import BaseSkill
from config.settings import settings
from src.utils.llm_factory import get_llm
from src.utils.llm_response import parse_json_from_llm

logger = logging.getLogger(__name__)


class CaseRetrieverSkill(BaseSkill):
    """
    案例检索Skill（LLM驱动版）

    功能：
    - 根据合同条款语义检索相关案例（向量搜索）
    - 使用LLM评估案例与合同的相关性
    - 提供案例摘要和判决要点
    """

    # 本地回退案例库
    FALLBACK_CASES = [
        {
            "id": "case_001", "title": "XX公司诉YY公司合同纠纷案",
            "category": "违约责任",
            "summary": "法院认定合同约定的违约金过高，依法调整为实际损失的30%。",
            "reference": "《民法典》第585条", "risk_level": "high",
        },
        {
            "id": "case_002", "title": "张某诉某科技公司劳动合同纠纷",
            "category": "劳动争议",
            "summary": "公司未支付加班费，法院判决公司支付加班费及经济补偿。",
            "reference": "《劳动法》第44条", "risk_level": "high",
        },
        {
            "id": "case_003", "title": "某消费者诉某电商平台格式条款纠纷",
            "category": "格式条款",
            "summary": "电商平台'一经售出概不退换'的格式条款被认定无效。",
            "reference": "《消费者权益保护法》第26条", "risk_level": "medium",
        },
        {
            "id": "case_007", "title": "某保密协议纠纷案",
            "category": "保密条款",
            "summary": "公司约定了竞业限制但未支付补偿金，法院判定竞业限制条款无效。",
            "reference": "《劳动合同法》第23条", "risk_level": "high",
        },
        {
            "id": "case_008", "title": "某仲裁条款效力纠纷",
            "category": "争议解决",
            "summary": "合同同时约定仲裁和诉讼，仲裁条款被认定无效。",
            "reference": "《仲裁法》第5条", "risk_level": "medium",
        },
    ]

    def __init__(self):
        super().__init__(
            skill_id="case_retriever",
            name="案例检索",
            description="根据合同条款语义检索相关法律案例和判例",
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
                logger.warning(f"Qdrant连接失败，使用本地回退: {e}")
                self._vector_store = False
        return self._vector_store

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行案例检索

        Args:
            **kwargs:
                - query: 搜索关键词或语义查询
                - category: 案例类别（可选）
                - risk_level: 风险等级筛选（可选）
                - keywords: 关键词列表（可选，忽略）
                - top_k: 返回数量（默认5）

        Returns:
            检索结果
        """
        query = kwargs.get("query", "")
        category = kwargs.get("category", "")
        risk_level = kwargs.get("risk_level", "")
        top_k = kwargs.get("top_k", 5)

        try:
            # 尝试向量搜索
            if self.vector_store and self.vector_store is not False:
                results = self._vector_search(query, category, risk_level, top_k)
                search_method = "vector"
            else:
                # 回退到LLM相关性评估
                results = await self._llm_search(query, category, risk_level, top_k)
                search_method = "llm"

            return {
                "total_found": len(results),
                "cases": results,
                "search_method": search_method,
                "search_params": {
                    "query": query,
                    "category": category,
                    "risk_level": risk_level,
                },
            }
        except Exception as e:
            logger.error(f"案例检索失败: {e}")
            results = await self._llm_search(query, category, risk_level, top_k)
            return {
                "total_found": len(results),
                "cases": results,
                "search_method": "llm_fallback",
                "search_params": {"query": query, "category": category},
            }

    async def _llm_search(
        self, query: str, category: str, risk_level: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """使用LLM评估案例相关性"""
        llm = get_llm()

        # 构建案例列表
        cases_text = "\n".join([
            f"- {c['id']}: {c['title']} | 类别: {c['category']} | 摘要: {c['summary']}"
            for c in self.FALLBACK_CASES
        ])

        filter_hint = ""
        if category:
            filter_hint += f"\n筛选类别: {category}"
        if risk_level:
            filter_hint += f"\n筛选风险等级: {risk_level}"

        system_prompt = f"""你是一个法律案例检索专家。请从以下案例库中找出与查询最相关的案例。

案例库：
{cases_text}
{filter_hint}

输出格式要求（必须是严格有效的JSON数组）：
[
  {{
    "id": "案例ID",
    "relevance_score": 0.85,
    "reason": "相关原因"
  }}
]

按相关性从高到低排序，返回最多{top_k}个。只输出JSON数组，不要其他内容"""

        user_message = f"查询: {query}" if query else "请列出所有相关案例"

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)

            result = parse_json_from_llm(content)

            if isinstance(result, list):
                # 合并案例详情
                case_map = {c["id"]: c for c in self.FALLBACK_CASES}
                enriched = []
                for item in result:
                    case_id = item.get("id", "")
                    if case_id in case_map:
                        enriched.append({
                            **case_map[case_id],
                            "relevance_score": item.get("relevance_score", 0),
                            "reason": item.get("reason", ""),
                        })
                return enriched[:top_k]
        except Exception as e:
            logger.error(f"LLM案例检索失败: {e}")

        # 回退：返回所有案例
        return self.FALLBACK_CASES[:top_k]

    def _vector_search(
        self, query: str, category: str, risk_level: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """向量搜索"""
        filters = {}
        if category:
            filters["category"] = category
        if risk_level:
            filters["risk_level"] = risk_level

        return self.vector_store.search(
            collection_name=settings.QDRANT_COLLECTION_CASES,
            query=query,
            top_k=top_k,
            filters=filters if filters else None,
        )

    def get_cases_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取案例"""
        if self.vector_store and self.vector_store is not False:
            return self._vector_search("", category, "", 20)
        return [c for c in self.FALLBACK_CASES if c["category"] == category]

    def get_high_risk_cases(self) -> List[Dict[str, Any]]:
        """获取高风险案例"""
        if self.vector_store and self.vector_store is not False:
            return self._vector_search("", "", "high", 20)
        return [c for c in self.FALLBACK_CASES if c["risk_level"] == "high"]
