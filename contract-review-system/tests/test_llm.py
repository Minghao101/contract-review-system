"""
LLM测试模块
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.llm_factory import get_llm


def test_llm_connection():
    """测试LLM连接"""
    print("正在测试LLM连接...")

    try:
        llm = get_llm()
        print(f"LLM实例创建成功: {type(llm).__name__}")

        # 测试简单调用
        response = llm.invoke("你好，请简单介绍一下自己")
        print(f"LLM响应: {response.content[:100]}...")

        print("LLM测试通过！")
        return True
    except Exception as e:
        print(f"LLM测试失败: {e}")
        return False


if __name__ == "__main__":
    test_llm_connection()
