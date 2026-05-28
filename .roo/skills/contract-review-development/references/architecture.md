# 智能合同审查系统 - 架构参考

## 开发状态 (截至 2026-05-28)

### 已完成模块

| 模块 | 文件 | 状态 |
|------|------|------|
| BaseAgent 基类 | `src/agents/base_agent.py` | ✅ 完成 |
| CoordinatorAgent | `src/agents/coordinator_agent.py` | ✅ 完成 |
| DocumentParserAgent | `src/agents/document_parser_agent.py` | ✅ 完成 |
| ClauseAnalysisAgent | `src/agents/clause_analysis_agent.py` | ✅ 完成 |
| RiskAssessmentAgent | `src/agents/risk_assessment_agent.py` | ✅ 完成 |
| ComplianceCheckerAgent | `src/agents/compliance_checker_agent.py` | ✅ 完成 |
| ReportGeneratorAgent | `src/agents/report_generator_agent.py` | ✅ 完成 |
| Agent通信 | `src/agents/communication.py` | ✅ 完成 |
| AgentTools集成 | `src/agents/agent_tools.py` | ✅ 完成 |
| 记忆系统 | `src/memory/` | ✅ 完成 |
| MCP Server/Client | `src/mcp/` | ✅ 完成 |
| 12个Skills | `src/skills/` | ✅ 完成 |
| FastAPI API | `src/api/` | ✅ 完成 |
| LLM工厂 | `src/utils/llm_factory.py` | ✅ 完成 |
| 配置管理 | `config/settings.py` | ✅ 完成 |

### 待开发模块

| 模块 | 内容 | 优先级 |
|------|------|--------|
| 工具集成测试 | 测试所有工具集成、修复问题 | 高 |
| Agent协作测试 | 端到端测试、Agent间通信 | 高 |
| 记忆系统测试 | 并发性能、通知机制 | 中 |
| 工作流测试 | LangGraph工作流、条件路由 | 中 |
| 性能优化 | 瓶颈分析、优化处理逻辑 | 中 |
| 错误处理 | 全局错误处理、重试机制 | 中 |
| 前端UI | 对话界面、文件上传 | 低 |
| 多轮对话 | 上下文管理、意图识别 | 低 |

---

## 1. 系统整体架构

```
用户上传文件/输入指令
        ↓
   FastAPI 后端 (src/api/main.py)
        ↓
   TaskManager (src/api/task_manager.py)
   意图识别 → Agent 路由 → 执行 → 结果汇总
        ↓
   CoordinatorAgent (src/agents/coordinator_agent.py)
   LLM 智能规划 → 动态执行计划 → 并行/串行调度
        ↓
   ┌────────────┬────────────┬────────────┬────────────┐
   ↓            ↓            ↓            ↓            ↓
 Document    Clause      Risk       Compliance   Report
 Parser      Analysis    Assessment  Checker     Generator
 Agent       Agent       Agent       Agent       Agent
   ↓            ↓            ↓            ↓            ↓
   └────────────┴────────────┴────────────┴────────────┘
                        ↓
                   最终审查结果
```

## 2. Agent 角色定义

### 2.1 BaseAgent 基类 (`src/agents/base_agent.py`)

所有 Agent 的抽象基类，定义统一接口：

```python
class BaseAgent(ABC):
    agent_id: str          # 唯一标识符
    name: str              # 显示名称
    role: str              # 角色标识（用于路由匹配）
    llm: BaseLLM           # LLM 实例（通过 get_llm() 获取）
    private_memory: Dict   # 私有记忆存储

    @abstractmethod
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务的抽象方法，子类必须实现"""
```

### 2.2 六个核心 Agent

| Agent | role | 职责 | 输入 | 输出 |
|-------|------|------|------|------|
| **CoordinatorAgent** | `coordinator` | 智能任务调度、LLM 动态规划、结果汇总 | 合同文本 + 类型 + 审查重点 | 完整审查结果 |
| **DocumentParserAgent** | `document_parser` | 合同文档预处理、结构化信息提取 | contract_text, contract_type | document_info, structure |
| **ClauseAnalysisAgent** | `clause_analyst` | 条款完整性、歧义检测、权利义务平衡分析 | contract_text, review_focus | sections, analysis |
| **RiskAssessmentAgent** | `risk_assessor` | 风险识别、量化、缓解建议 | contract_text, contract_type | risks, risk_level, mitigation_plan |
| **ComplianceCheckerAgent** | `compliance_checker` | 法规合规检查、必备条款验证 | contract_text, contract_type | compliance_status, score, violations |
| **ReportGeneratorAgent** | `report_generator` | 汇总所有分析结果，生成审查报告 | previous_results | report, summary |

### 2.3 CoordinatorAgent 执行计划

默认执行计划（LLM 失败时的回退）：

```
Step 1: parse_document (串行)
    ↓
Step 2: [analyze_clauses, assess_risks, compliance_check] (并行)
    ↓
Step 3: generate_report (串行，汇总所有结果)
```

CoordinatorAgent 使用 LLM 动态规划，可根据任务需求调整执行顺序和并行策略。

## 3. 记忆系统 (`src/memory/`)

### 3.1 分层架构

```
SharedMemoryManager (shared_memory.py)
├── Redis 存储（键值对）
├── ChromaDB 向量存储（语义搜索）
└── Redis Pub/Sub（Agent 间通知）

AgentPrivateMemory (private_memory.py)
├── ConversationBufferMemory（上下文窗口）
├── 上下文压缩机制
└── 任务状态跟踪
```

### 3.2 记忆层次 (`memory_layer.py`)

```python
class MemoryLayer:
    CONTEXT = "context"      # 合同上下文（解析结果）
    ANALYSIS = "analysis"    # 分析结果（条款/风险/合规）
    DECISION = "decision"    # 决策历史（协调器决策）
```

### 3.3 数据流

1. DocumentParserAgent → 写入 `CONTEXT` 层（document_structure, metadata）
2. ClauseAnalysisAgent → 读取 `CONTEXT`，写入 `ANALYSIS`（clause_analysis）
3. RiskAssessmentAgent → 读取 `CONTEXT`，写入 `ANALYSIS`（risks, risk_scores）
4. ComplianceCheckerAgent → 读取 `CONTEXT`，写入 `ANALYSIS`（compliance_results）
5. ReportGeneratorAgent → 读取所有 `ANALYSIS`，生成最终报告

## 4. Skills 系统 (`src/skills/`)

### 4.1 架构

```
BaseSkill (base_skill.py) — 抽象基类
    ↓
SkillRegistry (skill_registry.py) — 注册和发现
    ├── document/ — 文档处理
    │   ├── PDFReaderSkill (pdf_reader.py)
    │   ├── DocxParserSkill (docx_parser.py)
    │   └── OCRProcessorSkill (ocr_processor.py)
    ├── legal/ — 法律分析
    │   ├── ClauseParserSkill (clause_parser.py)
    │   ├── RegulationCheckerSkill (regulation_checker.py)
    │   └── CaseRetrieverSkill (case_retriever.py)
    ├── risk/ — 风险管理
    │   ├── RiskIdentifierSkill (risk_identifier.py)
    │   ├── RiskScorerSkill (risk_scorer.py)
    │   └── MitigationSuggesterSkill (mitigation_suggester.py)
    └── report/ — 报告生成
        ├── ReportGeneratorSkill (report_generator.py)
        ├── VisualizationSkill (visualization.py)
        └── ExportSkill (export.py)
```

### 4.2 Agent 与 Skill 的关系

Agent 通过 [`AgentTools`](contract-review-system/src/agents/agent_tools.py) 调用 Skills，Skills 提供具体的工具能力。Agent 负责 LLM 推理和决策，Skills 负责执行具体操作。

## 5. MCP 系统 (`src/mcp/`)

### 5.1 组件

- **MCPServer** (`server.py`): MCP 服务端，注册工具和资源，处理 JSON-RPC 2.0 请求
- **MCPClient** (`client.py`): MCP 客户端，调用远程工具
- **Protocol** (`protocol.py`): MCP 协议定义（MCPRequest, MCPResponse, MCPTool, MCPResource）

### 5.2 支持的方法

- `initialize` — 初始化握手
- `tools/list` — 列出可用工具
- `tools/call` — 调用工具
- `resources/list` — 列出可用资源
- `resources/read` — 读取资源
- `ping` — 健康检查

## 6. API 层 (`src/api/`)

### 6.1 端点

```
POST /api/v1/upload       — 上传合同文件
POST /api/v1/review       — 提交审查请求
POST /api/v1/review/sync  — 同步审查（等待结果）
GET  /api/v1/tasks/{id}   — 查询任务状态
```

### 6.2 处理流程

```
HTTP 请求 → FastAPI 路由 (routes.py)
    → TaskManager (task_manager.py) — 任务创建和管理
    → CoordinatorAgent — 智能调度
    → 各专业 Agent — 执行分析
    → 结果返回
```

## 7. 配置系统 (`config/settings.py`)

使用 Pydantic `BaseSettings`，支持 `.env` 文件覆盖：

| 配置组 | 关键配置项 |
|--------|-----------|
| LLM | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE` |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` |
| RabbitMQ | `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_URL` |
| ChromaDB | `CHROMA_PERSIST_DIRECTORY`, `EMBEDDING_MODEL` |
| Agent | `MAX_CONCURRENT_AGENTS`, `AGENT_TIMEOUT` |
| 合同 | `CONTRACT_TYPES`, `MANDATORY_CLAUSES` |
