"""
初始化Qdrant向量数据库 - 导入法规和案例数据
"""
import sys
import io
import json
from pathlib import Path

# 修复Windows GBK编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.vector_store import get_vector_store
from config.settings import settings


def init_regulations():
    """导入法规数据"""
    data_file = project_root / "src" / "data" / "regulations.json"
    with open(data_file, "r", encoding="utf-8") as f:
        regulations = json.load(f)

    store = get_vector_store()
    store.add_documents(
        collection_name=settings.QDRANT_COLLECTION_REGULATIONS,
        documents=regulations,
        text_field="content",
    )
    print(f"✅ 导入 {len(regulations)} 条法规到 {settings.QDRANT_COLLECTION_REGULATIONS}")


def init_cases():
    """导入案例数据"""
    data_file = project_root / "src" / "data" / "cases.json"
    with open(data_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    store = get_vector_store()
    store.add_documents(
        collection_name=settings.QDRANT_COLLECTION_CASES,
        documents=cases,
        text_field="summary",
    )
    print(f"✅ 导入 {len(cases)} 条案例到 {settings.QDRANT_COLLECTION_CASES}")


def init_memory():
    """初始化长期记忆集合（空集合，后续使用时自动写入）"""
    store = get_vector_store()
    store._ensure_collection(settings.QDRANT_COLLECTION_MEMORY)
    print(f"✅ 初始化集合: {settings.QDRANT_COLLECTION_MEMORY}")


def main():
    print(f"连接Qdrant: {settings.QDRANT_URL}")
    print("=" * 50)

    try:
        init_regulations()
        init_cases()
        init_memory()
        print("=" * 50)
        print("✅ 向量数据库初始化完成！")

        # 显示集合信息
        store = get_vector_store()
        for name in [settings.QDRANT_COLLECTION_REGULATIONS, settings.QDRANT_COLLECTION_CASES, settings.QDRANT_COLLECTION_MEMORY]:
            info = store.get_collection_info(name)
            print(f"  {name}: {info.get('points_count', 0)} 条记录")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        print("请确保Qdrant服务已启动:")
        print("  docker run -p 6333:6333 qdrant/qdrant")
        sys.exit(1)


if __name__ == "__main__":
    main()
