"""
长期记忆模块 - 基于Qdrant向量数据库的持久化记忆

支持：
- 合同审查历史记忆
- 用户偏好记忆
- 跨会话记忆延续
- 语义检索历史记忆
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from config.settings import settings
from src.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    长期记忆 - 基于Qdrant向量存储

    记忆类型：
    - review: 合同审查历史（合同摘要、审查结果、关键发现）
    - preference: 用户偏好（常用合同类型、关注的风险点等）
    - knowledge: 知识积累（从审查中学习到的经验）
    """

    def __init__(self):
        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = get_vector_store()
        return self._store

    def _ensure_collection(self):
        """确保记忆集合存在"""
        self.store._ensure_collection(settings.QDRANT_COLLECTION_MEMORY)

    def save_review_memory(
        self,
        contract_name: str,
        contract_text: str,
        result: Dict[str, Any],
        user_id: str = "default",
    ):
        """
        保存合同审查记忆

        Args:
            contract_name: 合同名称
            contract_text: 合同文本（前500字作为摘要）
            result: 审查结果
            user_id: 用户ID
        """
        self._ensure_collection()

        # 构建记忆文本（用于向量化）
        summary_parts = [f"合同: {contract_name}"]

        if result.get("document_info"):
            info = result["document_info"]
            if info.get("contract_type"):
                summary_parts.append(f"类型: {info['contract_type']}")
            if info.get("basic_info", {}).get("parties"):
                summary_parts.append(f"当事方: {', '.join(info['basic_info']['parties'])}")

        if result.get("risks"):
            risk_titles = [r.get("title", "") for r in result["risks"][:3]]
            summary_parts.append(f"风险: {', '.join(risk_titles)}")

        if result.get("compliance_violations"):
            summary_parts.append(f"合规问题: {len(result['compliance_violations'])}条")

        if result.get("missing_clauses"):
            summary_parts.append(f"缺失条款: {len(result['missing_clauses'])}条")

        memory_text = " | ".join(summary_parts)

        # 构建payload
        payload = {
            "type": "review",
            "user_id": user_id,
            "contract_name": contract_name,
            "contract_summary": contract_text[:500],
            "memory_text": memory_text,
            "result_summary": {
                "status": result.get("status"),
                "risk_level": result.get("risk_level"),
                "compliance_score": result.get("compliance_score") or result.get("score"),
                "risks_count": len(result.get("risks", [])),
                "violations_count": len(result.get("compliance_violations", [])),
            },
            "created_at": datetime.now().isoformat(),
        }

        # 写入向量数据库
        self.store.add_documents(
            collection_name=settings.QDRANT_COLLECTION_MEMORY,
            documents=[payload],
            text_field="memory_text",
        )
        logger.info(f"保存审查记忆: {contract_name}")

    def save_preference(
        self,
        preference_key: str,
        preference_value: str,
        user_id: str = "default",
    ):
        """
        保存用户偏好

        Args:
            preference_key: 偏好键（如 "关注的风险类型"）
            preference_value: 偏好值（如 "知识产权,违约责任"）
            user_id: 用户ID
        """
        self._ensure_collection()

        payload = {
            "type": "preference",
            "user_id": user_id,
            "memory_text": f"{preference_key}: {preference_value}",
            "preference_key": preference_key,
            "preference_value": preference_value,
            "created_at": datetime.now().isoformat(),
        }

        self.store.add_documents(
            collection_name=settings.QDRANT_COLLECTION_MEMORY,
            documents=[payload],
            text_field="memory_text",
        )
        logger.info(f"保存偏好: {preference_key}")

    def save_knowledge(
        self,
        topic: str,
        content: str,
        source: str = "review",
    ):
        """
        保存知识积累

        Args:
            topic: 知识主题
            content: 知识内容
            source: 来源（review/manual）
        """
        self._ensure_collection()

        payload = {
            "type": "knowledge",
            "user_id": "system",
            "memory_text": f"{topic}: {content}",
            "topic": topic,
            "content": content,
            "source": source,
            "created_at": datetime.now().isoformat(),
        }

        self.store.add_documents(
            collection_name=settings.QDRANT_COLLECTION_MEMORY,
            documents=[payload],
            text_field="memory_text",
        )
        logger.info(f"保存知识: {topic}")

    def recall(
        self,
        query: str,
        memory_type: Optional[str] = None,
        user_id: str = "default",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        语义检索记忆

        Args:
            query: 查询文本
            memory_type: 记忆类型过滤（review/preference/knowledge/None=全部）
            user_id: 用户ID过滤
            top_k: 返回数量

        Returns:
            相关记忆列表
        """
        filters = {}
        if memory_type:
            filters["type"] = memory_type
        if user_id:
            filters["user_id"] = user_id

        results = self.store.search(
            collection_name=settings.QDRANT_COLLECTION_MEMORY,
            query=query,
            top_k=top_k,
            filters=filters if filters else None,
        )

        return results

    def get_review_history(
        self,
        user_id: str = "default",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取用户的审查历史"""
        return self.recall(
            query="合同审查历史",
            memory_type="review",
            user_id=user_id,
            top_k=top_k,
        )

    def get_preferences(
        self,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """获取用户偏好"""
        return self.recall(
            query="用户偏好设置",
            memory_type="preference",
            user_id=user_id,
            top_k=20,
        )

    def delete_memory(self, memory_id: int):
        """删除指定记忆"""
        try:
            self.store.client.delete(
                collection_name=settings.QDRANT_COLLECTION_MEMORY,
                points_selector=[memory_id],
            )
        except Exception as e:
            logger.warning(f"删除记忆失败: {e}")


# 全局单例
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """获取长期记忆单例"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
