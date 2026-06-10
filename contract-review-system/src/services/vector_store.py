"""
Qdrant向量存储服务 - 法规和案例的向量检索
"""
import os
import logging
from typing import Any, Dict, List, Optional
from sentence_transformers import SentenceTransformer
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

# 设置HuggingFace镜像（国内加速）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


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
            # 尝试连接远程Qdrant
            self.client = QdrantClient(url=settings.QDRANT_URL, timeout=3)
            self.client.get_collections()
            logger.info(f"已连接Qdrant: {settings.QDRANT_URL}")
        except Exception:
            # 连接失败，使用内存模式
            logger.info("Qdrant不可用，使用内存模式")
            self.client = QdrantClient(":memory:")
        self._embedding_model = None

    @property
    def embedding_model(self) -> SentenceTransformer:
        """延迟加载embedding模型"""
        if self._embedding_model is None:
            logger.info(f"加载embedding模型: {settings.EMBEDDING_MODEL}")
            self._embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._embedding_model

    def _ensure_collection(self, collection_name: str, dimension: int = 384):
        """确保集合存在"""
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
        embeddings = self.embedding_model.encode(texts, show_progress_bar=False)

        # 构造点
        points = []
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            point = PointStruct(
                id=i + 1,
                vector=embedding.tolist(),
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
        query_vector = self.embedding_model.encode([query])[0].tolist()

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
