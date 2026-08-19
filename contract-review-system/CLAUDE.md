# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 LangChain + LangGraph 的智能合同审查系统，使用多Agent协作架构。

## 常用命令

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_agent_collaboration.py -v

# 运行指定测试
python -m pytest tests/test_agent_collaboration.py::test_function_name -v

# 代码格式化
black src/ tests/

# 代码检查
ruff check src/ tests/

# 类型检查
mypy src/
```

## 代码架构

### 核心组件

```
src/
├── agents/           # Agent实现
│   ├── base_agent.py         # 基类，所有Agent继承此类
│   ├── coordinator_agent.py  # 协调器，负责任务调度
│   ├── communication.py      # Agent间消息通信（MessageBus）
│   └── langchain_agent.py    # LangChain Agent包装器
├── memory/           # 共享记忆系统
│   ├── shared_memory.py      # 分层存储（CONTEXT/ANALYSIS/DECISION）
│   ├── private_memory.py     # Agent私有记忆
│   └── memory_layer.py       # 记忆层次定义
├── tools/            # LangChain Tools
├── workflow/         # LangGraph工作流
└── utils/            # 工具函数
```

### Agent协作流程

1. **CoordinatorAgent** 接收任务并分发
2. **DocumentParserAgent** 解析合同文本
3. **ClauseAnalysisAgent** 分析条款
4. **RiskAssessmentAgent** 评估风险
5. **ComplianceCheckerAgent** 检查合规性
6. **ReportGeneratorAgent** 生成报告

Agent通过 `MessageBus` 通信，通过 `SharedMemoryManager` 共享数据。

### 记忆层次

- `CONTEXT` - 原始数据（合同文本等）
- `ANALYSIS` - 分析结果
- `DECISION` - 最终决策

## 开发规范

- Python 3.10+
- 异步优先：Agent方法使用 `async def`
- 所有Agent继承 `BaseAgent` 并实现 `process()` 方法
- 使用 `ChatPromptTemplate` 和 Pydantic 模型进行结构化输出
- 测试使用 `pytest-asyncio`

## 插件

本项目安装了 ponytail 插件，使用以下命令：
- `/ponytail-review` - 审查代码过度工程
- `/ponytail-audit` - 审查整个仓库
