"""
Qdrant向量存储服务 - 法规和案例的向量检索
"""
import os
import logging
from typing import Any, Dict, List, Optional
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from config.settings import settings

logger = logging.getLogger(__name__)

# DashScope Embedding 客户端（延迟初始化）
_dashscope_embedder = None


def _get_dashscope_embedder():
    """获取 DashScope Embedding 客户端"""
    global _dashscope_embedder
    if _dashscope_embedder is None:
        from llama_index.embeddings.dashscope import DashScopeEmbedding
        _dashscope_embedder = DashScopeEmbedding(
            model_name=settings.EMBEDDING_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
        )
        logger.info(f"初始化 DashScope Embedding: {settings.EMBEDDING_MODEL}")
    return _dashscope_embedder


class QdrantVectorStore:
    """
    Qdrant向量存储服务

    功能：
    - 法规条款向量化存储和检索
    - 案例向量化存储和检索
    - 语义相似度搜索
    - 按类别/风险等级过滤
    """

    def __init__(self):
        try:
            self.client = QdrantClient(url=settings.QDRANT_URL, timeout=3)
            self.client.get_collections()
            logger.info(f"已连接Qdrant: {settings.QDRANT_URL}")
        except Exception:
            logger.info("Qdrant不可用，使用内存模式")
            self.client = QdrantClient(":memory:")
        self._http_client = httpx.Client(timeout=30)

    def _encode(self, texts: List[str]) -> List[List[float]]:
        """调用Embedding API获取向量"""
        if settings.EMBEDDING_PROVIDER == "dashscope":
            # 使用 DashScope Embedding
            embedder = _get_dashscope_embedder()
            return embedder.get_text_embedding_batch(texts)
        else:
            # 使用 Ollama Embedding (兼容旧模式)
            resp = self._http_client.post(
                settings.EMBEDDING_URL,
                json={"model": settings.EMBEDDING_MODEL, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            # 兼容 Ollama 格式: {"embeddings": [[...], ...]}
            if "embeddings" in data:
                return data["embeddings"]
            # 兼容 OpenAI 格式: {"data": [{"embedding": [...]}]}
            if "data" in data:
                return [item["embedding"] for item in data["data"]]
            raise ValueError(f"未知的embedding响应格式: {list(data.keys())}")

    def _ensure_collection(self, collection_name: str, dimension: int = None):
        """确保集合存在"""
        if dimension is None:
            dimension = settings.EMBEDDING_VECTOR_SIZE
        try:
            collections = self.client.get_collections().collections
            existing = [c.name for c in collections]
            if collection_name not in existing:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"创建集合: {collection_name}")
        except Exception as e:
            logger.warning(f"检查/创建集合失败: {e}")

    def add_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        text_field: str = "content",
    ):
        """
        批量添加文档到向量集合

        Args:
            collection_name: 集合名称
            documents: 文档列表，每个文档是dict
            text_field: 用于生成向量的文本字段名
        """
        self._ensure_collection(collection_name)

        texts = [doc.get(text_field, "") for doc in documents]
        if not texts:
            return

        # 批量编码
        embeddings = self._encode(texts)

        # 构造点
        points = []
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            point = PointStruct(
                id=i + 1,
                vector=embedding if isinstance(embedding, list) else embedding.tolist(),
                payload={**doc, "text": texts[i]},
            )
            points.append(point)

        # 写入
        self.client.upsert(
            collection_name=collection_name,
            points=points,
        )
        logger.info(f"写入 {len(points)} 条文档到 {collection_name}")

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        向量相似度搜索

        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件，如 {"category": "违约责任", "risk_level": "high"}

        Returns:
            搜索结果列表
        """
        query_vector = self._encode([query])[0]

        # 构造过滤条件
        must_conditions = []
        if filters:
            for key, value in filters.items():
                if value:
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        results = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                **(hit.payload or {}),
            }
            for hit in results.points
        ]

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """获取集合信息"""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception:
            return {"name": collection_name, "vectors_count": 0, "points_count": 0}

    def delete_collection(self, collection_name: str):
        """删除集合"""
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"删除集合: {collection_name}")
        except Exception as e:
            logger.warning(f"删除集合失败: {e}")


# 全局单例
_vector_store: Optional[QdrantVectorStore] = None


def get_vector_store() -> QdrantVectorStore:
    """获取向量存储单例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store
