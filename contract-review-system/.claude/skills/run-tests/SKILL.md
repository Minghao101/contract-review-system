---
name: run-tests
description: >
  当用户要求【运行测试】【执行测试】【测试代码】时自动启用此skill。
  触发关键词：运行测试、执行测试、跑测试、test
version: 0.1.0
argument-hint: "[测试文件路径，可选]"
---

# 测试运行Skill

执行项目测试并生成报告。

## 执行步骤

1. **运行测试**
   ```bash
   # 运行所有测试
   python -m pytest tests/ -v

   # 运行指定测试（如果有参数）
   python -m pytest {参数} -v
   ```

2. **输出结果**
   - 统计通过/失败数量
   - 显示失败详情（如有）
   - 输出测试覆盖率（如有）

## 示例
```
/run-tests
/run-tests tests/test_agent_collaboration.py
```
