"""
API测试模块
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

# 测试合同文本
SAMPLE_CONTRACT = """
技术服务合同

甲方：北京科技有限公司
乙方：上海软件有限公司

一、合同标的
乙方为甲方提供技术开发服务。

二、服务费用
服务总费用为人民币50万元。

三、违约责任
如甲方违约，应承担无限责任。
"""


def test_root():
    """测试根路径"""
    print("测试根路径...")
    response = client.get("/")
    assert response.status_code == 200
    assert "version" in response.json()
    print("  - 根路径测试通过")
    return True


def test_health():
    """测试健康检查"""
    print("测试健康检查...")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("  - 健康检查测试通过")
    return True


def test_submit_review():
    """测试提交审查任务"""
    print("测试提交审查任务...")
    response = client.post(
        "/api/v1/review",
        json={
            "contract_text": SAMPLE_CONTRACT,
            "contract_type": "service"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"
    print(f"  - 任务ID: {data['task_id']}")
    print("  - 提交审查测试通过")
    return True


def test_get_task_status():
    """测试查询任务状态"""
    print("测试查询任务状态...")
    # 先提交一个任务
    response = client.post(
        "/api/v1/review",
        json={"contract_text": SAMPLE_CONTRACT}
    )
    task_id = response.json()["task_id"]

    # 查询状态
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == task_id
    print(f"  - 任务状态: {data['status']}")
    print("  - 查询任务状态测试通过")
    return True


def test_list_tasks():
    """测试列出任务"""
    print("测试列出任务...")
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    print(f"  - 任务数量: {len(data['tasks'])}")
    print("  - 列出任务测试通过")
    return True


def test_sync_review():
    """测试同步审查"""
    print("测试同步审查...")
    response = client.post(
        "/api/v1/review/sync",
        json={
            "contract_text": SAMPLE_CONTRACT,
            "contract_type": "service"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "risk_level" in data
    print(f"  - 审查状态: {data['status']}")
    print(f"  - 风险等级: {data['risk_level']}")
    print("  - 同步审查测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行API测试")
    print("=" * 50)

    tests = [
        test_root(),
        test_health(),
        test_submit_review(),
        test_get_task_status(),
        test_list_tasks(),
        test_sync_review(),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
