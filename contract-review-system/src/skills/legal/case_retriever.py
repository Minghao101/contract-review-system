"""
案例检索Skill - 基于Qdrant向量检索相关法律案例和判例
"""
from typing import Any, Dict, List, Optional
import logging

from ..base_skill import BaseSkill
from config.settings import settings

logger = logging.getLogger(__name__)


class CaseRetrieverSkill(BaseSkill):
    """
    案例检索Skill

    功能：
    - 根据合同条款语义检索相关案例（向量搜索）
    - 按类别、风险等级过滤
    - 提供案例摘要和判决要点
    """

    # 本地回退案例库
    FALLBACK_CASES = [
        {
            "id": "case_001", "title": "XX公司诉YY公司合同纠纷案",
            "category": "违约责任", "keywords": ["违约金", "过高", "调整"],
            "summary": "法院认定合同约定的违约金过高，依法调整为实际损失的30%。",
            "reference": "《民法典》第585条", "risk_level": "high",
        },
        {
            "id": "case_002", "title": "张某诉某科技公司劳动合同纠纷",
            "category": "劳动争议", "keywords": ["加班费", "劳动时间", "加班"],
            "summary": "公司未支付加班费，法院判决公司支付加班费及经济补偿。",
            "reference": "《劳动法》第44条", "risk_level": "high",
        },
        {
            "id": "case_003", "title": "某消费者诉某电商平台格式条款纠纷",
            "category": "格式条款", "keywords": ["格式条款", "免责", "消费者"],
            "summary": "电商平台'一经售出概不退换'的格式条款被认定无效。",
            "reference": "《消费者权益保护法》第26条", "risk_level": "medium",
        },
        {
            "id": "case_007", "title": "某保密协议纠纷案",
            "category": "保密条款", "keywords": ["保密", "竞业限制", "补偿"],
            "summary": "公司约定了竞业限制但未支付补偿金，法院判定竞业限制条款无效。",
            "reference": "《劳动合同法》第23条", "risk_level": "high",
        },
        {
            "id": "case_008", "title": "某仲裁条款效力纠纷",
            "category": "争议解决", "keywords": ["仲裁", "诉讼", "管辖"],
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
                - keywords: 关键词列表（可选）
                - top_k: 返回数量（默认5）

        Returns:
            检索结果
        """
        query = kwargs.get("query", "")
        category = kwargs.get("category", "")
        risk_level = kwargs.get("risk_level", "")
        keywords = kwargs.get("keywords", [])
        top_k = kwargs.get("top_k", 5)

        # 组合查询文本
        search_text = query
        if keywords:
            search_text = f"{query} {' '.join(keywords)}" if query else " ".join(keywords)

        try:
            # 尝试向量搜索
            if self.vector_store and self.vector_store is not False:
                results = self._vector_search(search_text, category, risk_level, top_k)
            else:
                # 回退到本地搜索
                results = self._local_search(query, category, risk_level, keywords)

            return {
                "total_found": len(results),
                "cases": results,
                "search_method": "vector" if (self.vector_store and self.vector_store is not False) else "local",
                "search_params": {
                    "query": search_text,
                    "category": category,
                    "risk_level": risk_level,
                    "keywords": keywords,
                },
            }
        except Exception as e:
            logger.error(f"案例检索失败: {e}")
            # 回退到本地搜索
            results = self._local_search(query, category, risk_level, keywords)
            return {
                "total_found": len(results),
                "cases": results,
                "search_method": "fallback",
                "search_params": {"query": search_text, "category": category},
            }

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

    def _local_search(
        self, query: str, category: str, risk_level: str, keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """本地关键词搜索（回退）"""
        results = []
        keywords = keywords or []

        for case in self.FALLBACK_CASES:
            if category and case["category"] != category:
                continue
            if risk_level and case["risk_level"] != risk_level:
                continue

            score = 0
            if query:
                if query in case.get("title", ""):
                    score += 3
                if query in case.get("summary", ""):
                    score += 2
                for kw in case.get("keywords", []):
                    if query in kw or kw in query:
                        score += 1

            for kw in keywords:
                if kw in case.get("summary", "") or kw in case.get("title", ""):
                    score += 1

            if score > 0 or (not query and not category and not risk_level and not keywords):
                results.append({**case, "match_score": score})

        results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return results

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
