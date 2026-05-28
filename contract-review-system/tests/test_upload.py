"""
文件上传API测试
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

# 测试合同内容
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京科技有限公司
乙方：上海软件有限公司

一、合同标的
乙方为甲方提供技术开发服务，包括系统设计、编码实现和测试。

二、服务期限
合同有效期自2024年1月1日至2024年12月31日。

三、服务费用
服务总费用为人民币50万元，甲方应在合同签订后预付全款。

四、违约责任
如甲方违约，应承担无限责任，赔偿乙方一切损失。
"""


def test_upload_txt_file():
    """测试上传TXT文件"""
    print("测试TXT文件上传...")

    # 创建测试文件
    file_content = SAMPLE_CONTRACT.encode("utf-8")

    response = client.post(
        "/api/v1/upload",
        files={"file": ("test_contract.txt", file_content, "text/plain")},
        data={"contract_type": "service"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"
    assert data["file_type"] == "txt"
    assert data["total_chars"] > 0

    print(f"  - 任务ID: {data['task_id']}")
    print(f"  - 文件类型: {data['file_type']}")
    print(f"  - 字符数: {data['total_chars']}")
    print("TXT文件上传测试通过！")
    return True


def test_upload_sync():
    """测试同步上传"""
    print("测试同步上传...")

    file_content = SAMPLE_CONTRACT.encode("utf-8")

    response = client.post(
        "/api/v1/upload/sync",
        files={"file": ("test_contract.txt", file_content, "text/plain")},
        data={"contract_type": "service"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "file_info" in data
    assert data["file_info"]["filename"] == "test_contract.txt"

    print(f"  - 文件: {data['file_info']['filename']}")
    print(f"  - 类型: {data['file_info']['file_type']}")
    print("同步上传测试通过！")
    return True


def test_upload_invalid_format():
    """测试上传不支持的格式"""
    print("测试不支持格式上传...")

    file_content = b"test content"

    response = client.post(
        "/api/v1/upload",
        files={"file": ("test.exe", file_content, "application/octet-stream")},
    )

    assert response.status_code == 400

    print("  - 拒绝不支持的格式: .exe")
    print("格式验证测试通过！")
    return True


def test_upload_empty_file():
    """测试上传空文件"""
    print("测试空文件上传...")

    file_content = b"   "

    response = client.post(
        "/api/v1/upload",
        files={"file": ("empty.txt", file_content, "text/plain")},
    )

    assert response.status_code == 400

    print("  - 拒绝空文件")
    print("空文件验证测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行文件上传测试")
    print("=" * 50)

    tests = [
        test_upload_txt_file(),
        test_upload_sync(),
        test_upload_invalid_format(),
        test_upload_empty_file(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
