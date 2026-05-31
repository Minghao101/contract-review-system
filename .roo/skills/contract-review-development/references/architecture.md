# 架构参考文档

## 系统架构概览

智能合同审查系统采用五层架构，基于 LangChain + 多Agent协作模式。

### 架构图导航

完整的 Mermaid 架构图位于 `contract-review-system/architecture/` 目录：

| 文档 | 内容 | 图数量 |
|------|------|:---:|
| `architecture/README.md` | 系统全景图 + 设计原则 | 1 |
| `architecture/system-architecture.md` | 分层架构、模块依赖、时序图、类图 | 7 |
| `architecture/agent-workflow.md` | 多Agent协作、消息总线、调度机制 | 9 |
| `architecture/data-model.md` | 三层记忆、数据模型、数据流 | 7 |
| `architecture/infrastructure.md` | LLM/MCP/Redis/RabbitMQ/ChromaDB | 9 |

### 核心组件关系

```
FastAPI → TaskManager → CoordinatorAgent → [DocumentParser, ClauseAnalysis, RiskAssessment, ComplianceChecker, ReportGenerator]
                                    ↓
                              SharedMemoryManager (CONTEXT → ANALYSIS → DECISION)
                                    ↓
                              MCPServer ← SkillRegistry ← [DocumentSkills, LegalSkills, RiskSkills, ReportSkills]
```

### Agent 继承体系

所有 Agent 继承 `BaseAgent`（ABC），必须实现 `process(task: Dict) -> Dict` 方法。

### Skill 继承体系

所有 Skill 继承 `BaseSkill`（ABC），必须实现 `execute(**kwargs) -> Dict` 方法。通过 `SkillRegistry` 注册为 MCP 工具。

### MCP 协议

使用 JSON-RPC 2.0 协议，支持 `initialize`、`tools/list`、`tools/call`、`resources/list`、`resources/read`、`ping` 方法。

### 记忆层次

- **CONTEXT**: contract_text, structured_clauses, metadata, key_terms
- **ANALYSIS**: clause_analysis, risk_assessment, compliance_check
- **DECISION**: review_decisions, final_report, recommendations
