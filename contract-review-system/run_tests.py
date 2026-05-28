"""
Day 15: 工具集成测试运行脚本
运行所有集成测试并生成报告
"""
import sys
import os
import time
from pathlib import Path

# 添加项目根目录和tests目录到Python路径
project_root = Path(__file__).parent
tests_dir = project_root / "tests"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(tests_dir))

import test_skills_integration
import test_tools_integration
import test_agent_integration


def run_all():
    """运行所有测试"""
    print("=" * 70)
    print("  智能合同审查系统 - Day 15 工具集成测试")
    print("=" * 70)
    print()

    start_time = time.time()
    all_results = []

    # 1. Skills集成测试
    print("\n" + "=" * 70)
    print("  模块1: Skills全面集成测试 (12个Skills)")
    print("=" * 70)
    try:
        result = test_skills_integration.run_all_tests()
        all_results.append(("Skills集成测试", result))
    except Exception as e:
        print(f"  ✗ Skills集成测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        all_results.append(("Skills集成测试", False))

    # 2. LangChain Tools和AgentTools集成测试
    print("\n" + "=" * 70)
    print("  模块2: LangChain Tools和AgentTools集成测试")
    print("=" * 70)
    try:
        result = test_tools_integration.run_all_tests()
        all_results.append(("Tools集成测试", result))
    except Exception as e:
        print(f"  ✗ Tools集成测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        all_results.append(("Tools集成测试", False))

    # 3. Agent端到端集成测试
    print("\n" + "=" * 70)
    print("  模块3: Agent端到端集成测试")
    print("=" * 70)
    try:
        result = test_agent_integration.run_all_tests()
        all_results.append(("Agent集成测试", result))
    except Exception as e:
        print(f"  ✗ Agent集成测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        all_results.append(("Agent集成测试", False))

    # 汇总结果
    elapsed = time.time() - start_time
    passed = sum(1 for _, r in all_results if r)
    total = len(all_results)

    print("\n" + "=" * 70)
    print("  测试汇总")
    print("=" * 70)
    for name, result in all_results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}  {name}")
    print()
    print(f"  总计: {passed}/{total} 模块通过")
    print(f"  耗时: {elapsed:.2f}秒")
    print("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
