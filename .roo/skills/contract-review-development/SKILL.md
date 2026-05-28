---
name: contract-review-development
description: 智能合同审查系统（contract-review-system）开发辅助 Skill。基于 LangChain + LLM 多 Agent 架构，提供项目架构导航、编码规范、开发指南，用于高效开发和维护合同审查系统。
---

# 智能合同审查系统 - 开发辅助 Skill

## 项目概述

基于 LangChain + MIMO 模型的多 Agent 智能合同审查系统，支持劳动合同、采购合同、租赁合同、技术合同、服务合同的自动化审查。

**核心技术栈**: LangChain / LangGraph / FastAPI / Redis / ChromaDB / Pydantic

## 开发进度

| 阶段 | 天数 | 状态 | 内容 |
|------|------|------|------|
| 基础架构 | Day 1-5 | ✅ 完成 | 项目结构、LLM配置、BaseAgent、记忆系统、MCP Server |
| 核心Agent | Day 6-10 | ✅ 完成 | CoordinatorAgent、DocumentParser、ClauseAnalysis、RiskAssessment、ComplianceChecker |
| Skills开发 | Day 11-14 | ✅ 完成 | 12个Skills（document/legal/risk/report）+ SkillRegistry + AgentTools |
| API层 | 额外 | ✅ 完成 | FastAPI路由、TaskManager（RabbitMQ+持久化）、文件上传 |
| 工具集成测试 | Day 15 | 🔄 待开发 | 测试所有工具集成、修复问题、优化性能 |
| 集成测试 | Day 16-20 | 🔄 待开发 | Agent协作、记忆系统、工作流、性能优化、错误处理 |
| UI与多轮对话 | Day 21-25 | 🔄 待开发 | 前端UI、意图识别、多轮对话、结果展示、联调测试 |

**下一步**: Day 15 工具集成测试 → Day 16-20 集成测试 → Day 21-25 UI开发

## 快速导航

| 场景 | 参考文件 |
|------|----------|
| 了解项目架构、Agent 角色、数据流 | [architecture.md](references/architecture.md) |
| 编写代码时的命名、格式、模式规范 | [coding-conventions.md](references/coding-conventions.md) |
| 新增/修改 Agent、Skill、Tool、API 的开发流程 | [development-guide.md](references/development-guide.md) |

## 核心目录结构

```
contract-review-system/
├── src/
│   ├── agents/          # 6 个 Agent（BaseAgent 基类 + 5 个专业 Agent）
│   ├── memory/          # 记忆系统（SharedMemory + PrivateMemory）
│   ├── mcp/             # MCP Server/Client/Protocol
│   ├── skills/          # 12 个 Skill（document/legal/risk/report 四类）
│   ├── tools/           # LangChain Tools 集成
│   ├── api/             # FastAPI 后端 + TaskManager
│   └── utils/           # LLM 工厂、日志、验证器
├── config/settings.py   # Pydantic Settings 配置
├── tests/               # 测试用例
└── data/                # 样本数据和任务索引
```

## 关键入口文件

- 配置: [`config/settings.py`](contract-review-system/config/settings.py)
- Agent 基类: [`src/agents/base_agent.py`](contract-review-system/src/agents/base_agent.py)
- 协调器: [`src/agents/coordinator_agent.py`](contract-review-system/src/agents/coordinator_agent.py)
- API 入口: [`src/api/main.py`](contract-review-system/src/api/main.py)
- 任务管理: [`src/api/task_manager.py`](contract-review-system/src/api/task_manager.py)
- Skill 注册: [`src/skills/skill_registry.py`](contract-review-system/src/skills/skill_registry.py)
- 工具集成: [`src/agents/agent_tools.py`](contract-review-system/src/agents/agent_tools.py)

## 开发注意事项

1. **所有 Agent 必须继承 [`BaseAgent`](contract-review-system/src/agents/base_agent.py:12) 并实现 `process()` 抽象方法**
2. **LLM 调用通过 [`get_llm()`](contract-review-system/src/utils/llm_factory.py) 统一获取，不要直接实例化模型**
3. **新 Agent 需在 [`TaskManager`](contract-review-system/src/api/task_manager.py) 中注册**
4. **新 Skill 需继承 [`BaseSkill`](contract-review-system/src/skills/base_skill.py) 并在 [`SkillRegistry`](contract-review-system/src/skills/skill_registry.py) 中注册**
5. **MCP 工具需在 [`MCPServer`](contract-review-system/src/mcp/server.py) 中注册 handler**
6. **配置变更统一在 [`Settings`](contract-review-system/config/settings.py:11) 类中管理，通过 `.env` 覆盖**
