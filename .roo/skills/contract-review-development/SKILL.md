---
name: contract-review-development
description: 智能合同审查系统的开发指导，包含多Agent协作架构、LLM驱动分析、MCP协议通信、分层记忆系统等完整技术栈的开发规范和最佳实践。
---

# 智能合同审查系统 - 开发指导 Skill

## 概述

本 Skill 为智能合同审查系统（Contract Review System）的开发提供完整的技术指导。系统基于 LangChain + 多Agent协作架构，使用 MIMO 模型进行智能合同分析。

## 快速导航

### 架构理解
- **系统架构**: 查看 `contract-review-system/architecture/README.md` — 系统全景图和分层架构
- **详细架构**: 查看 `contract-review-system/architecture/system-architecture.md` — 分层、依赖、时序图
- **Agent工作流**: 查看 `contract-review-system/architecture/agent-workflow.md` — 多Agent协作流程
- **数据模型**: 查看 `contract-review-system/architecture/data-model.md` — 记忆层次和数据结构
- **基础设施**: 查看 `contract-review-system/architecture/infrastructure.md` — LLM/MCP/Redis/RabbitMQ

### 开发规范
- **编码规范**: 查看 `references/coding-conventions.md`
- **开发指南**: 查看 `references/development-guide.md`
- **架构参考**: 查看 `references/architecture.md`

## 核心架构要点

### 1. 五层架构
```
L1 接入层 → L2 业务编排层 → L3 专业Agent层 → L4 能力层 → L5 基础设施层
```

### 2. 五个核心 Agent
| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| CoordinatorAgent | 智能调度，LLM生成执行计划 | contract_text | 执行计划 |
| DocumentParserAgent | 文档解析，提取结构化信息 | contract_text | meta + clauses + key_terms |
| ClauseAnalysisAgent | 条款分析，完整性/歧义/公平性 | contract_text | clause_analysis |
| RiskAssessmentAgent | 风险评估，识别/评分/缓解 | contract_text + type | risk_assessment |
| ComplianceCheckerAgent | 合规检查，必备条款/法规 | contract_text + type | compliance_check |
| ReportGeneratorAgent | 报告生成，汇总所有分析 | previous_results | final_report |

### 3. 三层记忆
- **CONTEXT层**: 合同上下文（原始文档、结构化条款、元数据）
- **ANALYSIS层**: 分析结果（条款分析、风险评估、合规检查）
- **DECISION层**: 决策历史（审查决策、冲突解决、最终建议）

### 4. 执行流程
```
阶段1: 文档解析 → CONTEXT层
阶段2: 条款分析 + 风险评估 + 合规检查（并行） → ANALYSIS层
阶段3: 报告生成 → DECISION层
```

## 开发时的关键约定

1. **所有 Agent 继承 `BaseAgent`**，实现 `process(task) -> Dict` 方法
2. **所有 Skill 继承 `BaseSkill`**，实现 `execute(**kwargs) -> Dict` 方法
3. **Agent 使用 LLM 驱动**，正则作为回退方案
4. **共享记忆使用 `SharedMemoryManager`**，分层存储
5. **技能通过 `SkillRegistry` 注册为 MCP 工具**
6. **配置统一在 `config/settings.py`**，使用 Pydantic Settings

## 文件结构

```
contract-review-system/
├── src/
│   ├── agents/          # Agent实现（6个Agent）
│   ├── api/             # FastAPI接口
│   ├── mcp/             # MCP协议（Server/Client/Protocol）
│   ├── memory/          # 记忆系统（共享/私有/层次）
│   ├── skills/          # 技能库（文档/法律/风险/报告）
│   ├── tools/           # LangChain Tools
│   ├── utils/           # 工具函数（LLM工厂/日志/验证）
│   └── workflow/        # 工作流定义
├── config/              # 配置管理
├── data/                # 数据文件
├── tests/               # 测试代码
└── architecture/        # 架构文档（30+ Mermaid图）
```
