# 智能合同审查系统 — 项目技术分析文档

> LangChain + 多 Agent 事件驱动 + 弱中心化架构 + 四层记忆系统

---

## 一、项目概述

本项目是一个基于 LLM 的智能合同审查系统，采用多 Agent 协作架构，支持合同解析、风险评估、条款分析、合规检查和报告生成。系统通过事件驱动的弱中心化架构实现 Agent 间的自主协作，具备完整的容错降级能力和多轮对话支持。

### 核心能力

| 能力 | 说明 |
|------|------|
| 合同解析 | LLM 驱动的结构化信息提取，支持长文本 Map-Reduce |
| 风险评估 | 纯 LLM 风险识别 + 量化评分 + 缓解建议 |
| 条款分析 | 完整性评估 + 模糊条款识别 + 权利义务平衡分析 |
| 合规检查 | 法规合规检查 + 违规项识别 + 合规评分 |
| 报告生成 | 汇总前序 Agent 结果，LLM 生成结构化审查报告 |
| 增量修改 | 用户修改条款后只重新分析修改部分，合并到已有结果 |
| 议题讨论 | 多 Agent 围绕开放性议题给出专业意见（带置信度） |
| 多轮对话 | 追问、修改、单维度分析等多轮交互 |

---

## 二、技术架构

### 2.1 系统全景架构

```
┌──────────────────────────────────────────────────────┐
│              User Layer                               │
│  Streamlit 前端（聊天 + 文件上传）                       │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│              API Layer                                │
│  FastAPI REST API │ RabbitMQ │ TaskManager             │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│       Coordination Layer（启动协调者）                  │
│  MultiTurnHandler — 初始化共享内存 → 发布 task.created   │
│  IntentRecognizer — LLM Function Calling 意图识别      │
│  ConversationContext — 会话上下文管理                    │
└──────────┬───────────────────────┬───────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌────────────────────────────┐
│  SharedMemoryManager │  │  MessageBus（事件总线）       │
│  (数据交换中枢)        │  │  task.created               │
│                      │  │  document.parsed             │
│  CONTEXT 层          │  │  risk.analyzed               │
│  ├─ contract_text    │  │  clause.analyzed             │
│  ├─ contract_type    │  │  compliance.checked          │
│  └─ review_focus     │  │  task.completed              │
│                      │  └────────────────────────────┘
│  ANALYSIS 层         │           ▲
│  ├─ parsed_result    │           │ 订阅事件
│  ├─ risk_result      │           │
│  ├─ clause_result    │  ┌────────┴───────────────────┐
│  └─ compliance_result│  │       Agent Layer            │
│                      │  │  DocumentParser               │
│  DECISION 层         │  │  ClauseAnalysis               │
│  ├─ final_report     │  │  RiskAssessment               │
│  └─ risk_level       │  │  ComplianceChecker            │
└──────────────────────┘  │  ReportGenerator              │
                          │  (各自订阅事件→读共享内存→      │
                          │   执行→写共享内存→发布事件)     │
                          └──────────────────────────────┘
```

### 2.2 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Streamlit | 豆包风格聊天界面，SSE 流式输出 |
| API | FastAPI | RESTful API + SSE 流式响应 |
| 消息队列 | RabbitMQ | 异步任务分发 |
| Agent 框架 | LangChain | LLM 调用层 + Function Calling（不使用 Agent/Chain 高层抽象） |
| LLM | MIMO (xiaomimimo) | 通过 OpenAI 兼容 API 调用，关闭思考模式 |
| 向量数据库 | Qdrant | 长期记忆持久化 + 语义检索 |
| Embedding | bge-m3 (Ollama) | 向量化嵌入 |
| 工作流（备选） | LangGraph | 状态图实现（已保留，与事件驱动方案并存） |

### 2.3 LLM 工厂设计

统一管理 LLM 实例，所有 Agent 通过 `get_llm()` 获取，单例模式 + 懒加载：

```python
class LLMFactory:
    def create_llm(self, provider=None):
        if provider == "openai":
            return ChatOpenAI(
                model="mimo-v2.5",
                api_key="...",
                base_url="https://token-plan-cn.xiaomimimo.com/v1",
                temperature=0.3,
                max_tokens=10000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

    def get_llm(self):
        if self._llm is None:
            self._llm = self.create_llm()
        return self._llm
```

支持三种 Provider：Anthropic、OpenAI 兼容（当前使用）、Ollama 本地回退。

---

## 三、事件驱动协作机制

### 3.1 事件链路

```
用户发送 "审查合同"
    │
    ▼
MultiTurnHandler
    ├── 意图识别（LLM Function Calling）
    ├── 初始化 SharedMemoryManager（写入 CONTEXT 层）
    ├── 初始化 MessageBus
    ├── 绑定基础设施到所有 Agent
    └── 发布 task.created 事件
            │
            ▼
    DocumentParserAgent（订阅 task.created）
        ├── 从共享内存读取 contract_text
        ├── LLM 提取 + Map-Reduce
        ├── 写入 ANALYSIS 层 parsed_result
        └── 发布 document.parsed
                │
                ▼
    ┌───────────┼───────────┐
    ▼           ▼           ▼
RiskAssessor  ClauseAnalyst  ComplianceChecker
(订阅 document.parsed，并行执行)
    │           │           │
    ▼           ▼           ▼
写入 risk_    写入 clause_  写入 compliance_
result        result        result
    │           │           │
    └───────────┼───────────┘
                ▼
    ReportGeneratorAgent（聚合屏障归零后触发）
        ├── 从共享内存读取所有 ANALYSIS 层结果
        ├── LLM 生成报告
        ├── 写入 DECISION 层 final_report
        └── 发布 task.completed
                │
                ▼
    MultiTurnHandler 收到 task.completed
        ├── 从共享内存收集所有结果
        ├── 格式化回复
        └── 返回给前端
```

### 3.2 事件类型定义

```python
class BusinessEvent:
    TASK_CREATED = "task.created"
    DOCUMENT_PARSED = "document.parsed"
    RISK_ANALYZED = "risk.analyzed"
    CLAUSE_ANALYZED = "clause.analyzed"
    COMPLIANCE_CHECKED = "compliance.checked"
    CLAUSE_UPDATED = "clause.updated"
    TASK_COMPLETED = "task.completed"
```

### 3.3 聚合屏障（Aggregation Barrier）

解决「ReportGenerator 何时触发」的核心机制：

```python
# 初始化时写入 CONTEXT 层
_pending_count = len(required_agents) - 1  # 排除 DocumentParser

# 每个分析 Agent 完成后递减
pending = self.read_shared("_pending_count", MemoryLayer.CONTEXT)
if pending is not None and pending > 0:
    new_count = pending - 1
    self.write_shared("_pending_count", new_count, MemoryLayer.CONTEXT, validate=False)
    if new_count == 0:
        # 所有分析完成，触发 ReportGenerator
        self.publish_event(BusinessEvent.TASK_COMPLETED, {...})
```

### 3.4 按需调度

不同意图只执行需要的 Agent 子集，避免资源浪费：

```python
INTENT_REQUIRED_AGENTS = {
    IntentType.CONTRACT_REVIEW: ["document_parser", "risk_assessor", "clause_analyst", "compliance_checker", "report_generator"],
    IntentType.RISK_ASSESSMENT: ["document_parser", "risk_assessor"],
    IntentType.CLAUSE_ANALYSIS: ["document_parser", "clause_analyst"],
    IntentType.COMPLIANCE_CHECK: ["document_parser", "compliance_checker"],
    IntentType.REPORT_GENERATION: ["report_generator"],
}
```

### 3.5 意图识别（Function Calling）

基于 LLM Function Calling 的意图分类，零关键词匹配：

```python
class IntentResult(BaseModel):
    """用于 Function Calling 的结构化输出"""
    intent: IntentType
    confidence: float
    entities: Dict
    reasoning: str

async def _recognize_by_function_calling(self, text, context):
    structured_llm = self.llm.with_structured_output(IntentResult)
    result = await structured_llm.ainvoke(messages)
    return Intent(type=result.intent, confidence=result.confidence, ...)
```

| 意图类型 | 执行方式 | 需要合同 |
|---------|---------|---------|
| `contract_review` | 完整事件链（4 Agent） | 是 |
| `risk_assessment` | 单 Agent 执行 | 是 |
| `clause_analysis` | 单 Agent 执行 | 是 |
| `compliance_check` | 单 Agent 执行 | 是 |
| `question_answer` | LLM 直接回答 | 否 |
| `greeting` | 直接回复 | 否 |

---

## 四、弱中心化 vs 强中心化

### 4.1 为什么选择弱中心化

本项目经历了从强中心化到弱中心化的架构演进。核心驱动力：

**强中心化的本质问题：调度器知道太多。**

| 问题 | 强中心化的表现 | 弱中心化的解决方案 |
|------|-------------|----------------|
| 调度器膨胀 | 必须知道每个 Agent 需要什么字段、输出什么字段、何时触发 | Agent 自主决定读什么写什么 |
| 新增 Agent 高成本 | 每加一个 Agent 必须修改路由表 + 调度器逻辑 | 只需订阅事件 + 读写共享内存 |
| 单点瓶颈 | 所有 Agent 间通信都经过调度器中转 | Agent 通过共享内存直接交换数据 |
| 无法并行 | 调度器手动 `asyncio.gather()` 编排 | Agent 自主响应事件，并行执行 |
| 容错差 | 一个 Agent 失败 → 整个链路可能崩溃 | 单点故障不影响其他 Agent |
| 数据重复 | 每个 Agent 都收到完整的 task_context | Agent 只读取需要的字段 |

### 4.2 架构对比

**改造前（强中心化）：**
```
调度器 → _prepare_agent_input() → agent.process(task_context)
                                     ↓
                              返回 result → 调度器存储
```

**改造后（弱中心化）：**
```
调度器 → 初始化共享内存 → 发布 task.created
                              ↓
Agent 自主协作：读共享内存 → 执行 → 写共享内存 → 发布事件
                              ↓
调度器 ← 收集共享内存结果 → 格式化回复
```

### 4.3 核心优势

| 维度 | 强中心化 | 弱中心化 |
|------|---------|---------|
| **调度器角色** | 全知全能的指挥官 | 启动协调者 |
| **Agent 编排** | 手动 gather + 手动调用 ReportGenerator | Agent 自主协作，聚合屏障自动触发 |
| **数据传递** | 调度器手动构造 task_context | Agent 从共享内存按需读取 |
| **容错** | 向上传播，可能整链路崩溃 | try/finally 兜底，降级为错误结果 |
| **并行** | 调度器手动 gather | 事件驱动，天然并行 |
| **可扩展性** | 修改路由表 + 调度器逻辑 | Agent 订阅事件即可 |
| **数据契约** | 无（魔法字符串取值） | Pydantic Schema 校验 |
| **LLM 开销** | CoordinatorAgent 用 LLM 规划执行计划 | 静态列表直接确定，省一次 LLM 调用 |

### 4.4 实际收益

- 新增 Agent 从"修改 3 个文件"变为"新增 1 个文件"
- 调度器代码量减少 60%
- 单 Agent 崩溃不影响其他 Agent
- 更易测试：每个 Agent 可独立测试，不需要模拟整个调度器

---

## 五、四层记忆系统

### 5.1 架构设计

| 层级 | 模块 | 存储介质 | 用途 |
|------|------|----------|------|
| 对话上下文 | `ConversationContext` | 内存 | 维护多轮对话历史、消息轮次 |
| Agent 私有记忆 | `AgentPrivateMemory` | 内存 | 上下文窗口 + 压缩摘要 + TTL 缓存 + 任务状态 |
| 共享记忆 | `SharedMemoryManager` | 内存 | 三层数据交换中枢（CONTEXT/ANALYSIS/DECISION） |
| 长期记忆 | `LongTermMemory` | Qdrant 向量数据库 | 审查历史持久化 + 语义检索 |

### 5.2 共享内存三层分层

| 层级 | 用途 | 数据 | 写入者 | 读取者 |
|------|------|------|--------|--------|
| CONTEXT | 合同上下文（只读） | contract_text, contract_type, _required_agents, _pending_count | 调度器（一次性写入） | 所有 Agent |
| ANALYSIS | 分析结果 | parsed_result, risk_result, clause_result, compliance_result | 各 Agent 自主写入 | ReportGenerator |
| DECISION | 最终交付物 | final_report, risk_level | ReportGenerator | 调度器、前端 |

### 5.3 Schema 校验机制

核心业务数据写入共享内存时，自动通过 Pydantic Schema 校验：

```python
SHARED_DATA_SCHEMAS = {
    "parsed_result": DocumentParseResult,
    "risk_result": RiskAssessmentResult,
    "clause_result": ClauseAnalysisResult,
    "compliance_result": ComplianceCheckResult,
    "final_report": ReportResult,
}
```

写入时自动校验：
- `RiskAssessmentResult.risk_level` 必须是 `low/medium/high/critical`
- `ComplianceCheckResult.score` 必须在 0-100 范围内
- Schema 导入失败时降级为不校验，不阻塞主流程

### 5.4 Agent 私有记忆

每个 Agent 独立的记忆空间：
- `context_window`: 上下文窗口（deque，支持自动压缩）
- `compressed_summary`: 压缩后的摘要
- `task_state`: 执行状态（未开始/执行中/成功/失败）
- `cache`: 中间计算缓存（支持 TTL 过期）

---

## 六、三层容错设计

### 6.1 第一层：Agent 级 try/finally

每个 Agent 的 `process()` 方法用 `try/finally` 包裹，保证**事件必发**：

```python
async def process(self, task):
    self.set_running(True)
    try:
        result = await self._core_logic()
        self.write_shared(key, result, MemoryLayer.ANALYSIS)
        self.publish_event(BusinessEvent.XXX_ANALYZED, {...})
        return result
    except Exception as e:
        error_result = {"error": str(e), ...}
        self.write_shared(key, error_result, MemoryLayer.ANALYSIS)
        self.publish_event(BusinessEvent.XXX_ANALYZED, {...})
        return error_result
    finally:
        self.set_running(False)
```

设计原则：**无论成功失败，事件必须发布**，下游可以做降级处理。

### 6.2 第二层：调度器级 asyncio.wait_for

全局超时熔断，防止 Agent 卡死导致整个流程挂起：

```python
_TASK_TIMEOUT = 180  # 秒

result = await asyncio.wait_for(
    self._execute_event_driven(session_id),
    timeout=_TASK_TIMEOUT
)
```

超时后收集已有结果，降级返回部分审查结论。

### 6.3 第三层：部分失败降级

单个 Agent 失败不影响其他 Agent：

```python
results = await asyncio.gather(
    self._agents["risk_assessor"].process(task),
    self._agents["clause_analyst"].process(task),
    self._agents["compliance_checker"].process(task),
    return_exceptions=True
)
```

### 6.4 故障场景与处理

| 故障场景 | 处理方式 | 用户感知 |
|---------|---------|---------|
| Agent LLM 调用超时 | try/except 捕获，返回 error_result | 该维度分析缺失，其他维度正常 |
| Agent 进程卡死 | 全局超时 180s 熔断 | 返回已有的部分结果 |
| 共享内存写入失败 | write() 返回 -1，日志记录 | Agent 重试或降级 |
| 事件丢失（Agent 未发布事件） | 聚合屏障超时未归零 → 触发 ReportGenerator | 基于已有结果生成报告 |
| ReportGenerator 失败 | 返回基础报告（_generate_basic_report） | 简版报告 |

---

## 七、核心难点与解决方案

### 难点 1：Agent Singleton 与请求并发隔离

**问题：** Agent 是单例的（全局共享），但每个请求有独立的 SharedMemoryManager。如何让同一个 Agent 实例在处理不同请求时读写不同的共享内存？

**解决方案：** `RuntimeProxy` + `contextvars`

```python
class RuntimeProxy:
    def __init__(self, get_runtime_fn):
        self._get_runtime = get_runtime_fn

    def _get_sm(self):
        session_id = _current_session_id.get()  # contextvars 自动解析
        runtime = self._get_runtime(session_id)
        return runtime.shared_memory if runtime else None

    def read(self, agent_id, key, layer):
        sm = self._get_sm()
        return sm.read(agent_id, key, layer) if sm else None

    def write(self, agent_id, key, value, layer, validate=True):
        sm = self._get_sm()
        return sm.write(agent_id, key, value, layer, validate=validate) if sm else 0
```

Agent 绑定的是 proxy，proxy 在 read/write 时通过 `contextvars.ContextVar` 自动解析到当前 session 的 runtime。不需要修改 Agent 的 `process()` 签名，完全透明。

### 难点 2：聚合屏障 — ReportGenerator 何时触发

**问题：** 3 个分析 Agent 并行执行，ReportGenerator 必须等它们全部完成才能触发。但事件驱动架构中，调度器不知道 Agent 何时完成。

**解决方案：** 共享内存 CONTEXT 层维护 `_pending_count` 计数器。

- 初始化时写入 `_pending_count = len(required_agents) - 1`
- 每个分析 Agent 完成后递减
- 归零时触发回调 → 调度器收到通知 → 启动 ReportGenerator

### 难点 3：事件丢失的降级处理

**问题：** 如果某个 Agent 没有发布事件（比如崩溃了），聚合屏障永远不归零，流程卡死。

**解决方案：** `asyncio.wait_for(timeout=180s)` 全局超时熔断。超时后收集已有结果，降级返回部分审查结论。

### 难点 4：MIMO 模型思考模式的关闭

**问题：** MIMO (xiaomimimo) 模型默认开启思考模式（reasoning），但思考过程对前端用户无意义。

**尝试的方案：**
- `reasoning_effort=low` → 返回空内容
- `extra_body={"reasoning_effort": "low"}` → 无效

**最终方案：**
```python
extra_body={"chat_template_kwargs": {"enable_thinking": False}}
```
成功关闭思考模式，`reasoning=None`，正常输出内容。

### 难点 5：SSE 流式输出 + Agent 完成追踪

**问题：** 前端需要实时看到进度，但 Agent 是异步执行的。

**解决方案：**
- 用 SSE (Server-Sent Events) 逐条推送进度事件
- 订阅实际的**业务事件**（`document.parsed`、`risk.analyzed` 等）而非 Agent 完成事件
- 嵌套结果通过 `_flatten_results_for_display()` 扁平化后传给格式化器

### 难点 6：多 Agent 结果的格式化合并

**问题：** 不同 Agent 返回的字段结构不同，扁平化后可能冲突（比如 `missing_clauses` 同时出现在 ClauseAnalyst 和 ComplianceChecker 中）。

**解决方案：** `_flatten_results_for_display()` 中对列表类字段（`risks`、`missing_clauses`、`recommendations`）使用 `extend` 合并而非 `update` 覆盖。

---

## 八、项目独特之处

1. **不依赖 LangChain Agent/Chain 高层抽象** — 只用 LLM 调用层（ChatOpenAI/ChatAnthropic）+ 消息格式化，自己实现 Agent 协作逻辑。避免了 LangChain 框架的"过度抽象"问题。

2. **共享内存三层分层（CONTEXT/ANALYSIS/DECISION）** — 类似数据库的读写分离，CONTEXT 层只读、ANALYSIS 层各 Agent 自主写入、DECISION 层最终交付物。数据流清晰可控。

3. **Schema 校验 + 降级策略** — 核心数据强制 Pydantic 校验，校验失败拒绝写入。但 Schema 导入失败时降级为不校验，不会因为校验模块本身的问题阻塞主流程。

4. **同时支持两种架构** — `review_workflow.py` 中保留了 LangGraph 状态图的旧实现，`multi_turn_handler.py` 是新的事件驱动实现。可以随时切换对比。

5. **增量修改 vs 全量重跑** — 用户修改合同条款后，系统只重新分析修改的部分，合并到已有结果。这对实际业务中的"合同修改→重新审查"场景非常重要。

6. **议题板（TopicBoard）机制** — 用户可以发起"开放性讨论"，多个 Agent 围绕一个议题给出专业意见（带置信度和引用）。模拟了法律团队的协作讨论场景。

---

## 九、项目文件结构

```
contract-review-system/
├── config/
│   └── settings.py                  # 全局配置：LLM/Qdrant/Embedding/RabbitMQ
├── src/
│   ├── agents/
│   │   ├── base_agent.py            # Agent 基类：bind_infrastructure + read/write_shared
│   │   ├── business_events.py       # 标准业务事件常量
│   │   ├── shared_data_schemas.py   # Pydantic Schema：共享数据契约
│   │   ├── communication.py         # MessageBus 事件总线
│   │   ├── multi_turn_handler.py    # 核心：启动协调者 + RuntimeProxy
│   │   ├── intent_recognizer.py     # 意图识别：LLM Function Calling
│   │   ├── conversation_context.py  # 会话上下文管理
│   │   ├── document_parser_agent.py # 文档解析 Agent
│   │   ├── clause_analysis_agent.py # 条款分析 Agent
│   │   ├── risk_assessment_agent.py # 风险评估 Agent
│   │   ├── compliance_checker_agent.py # 合规检查 Agent
│   │   └── report_generator_agent.py   # 报告生成 Agent
│   ├── api/
│   │   ├── main.py                  # FastAPI 入口 + CORS
│   │   ├── routes.py                # API 路由 + SSE 流式输出
│   │   └── task_manager.py          # 任务管理 + 结果扁平化
│   ├── memory/
│   │   ├── shared_memory.py         # 共享内存：三层数据交换中枢
│   │   ├── private_memory.py        # Agent 私有记忆
│   │   ├── topic_board.py           # 议题板：多 Agent 讨论
│   │   ├── long_term_memory.py      # 长期记忆：Qdrant 向量存储
│   │   └── memory_layer.py          # 记忆层次枚举
│   ├── services/
│   │   └── vector_store.py          # Qdrant：bge-m3 Embedding + 向量检索
│   ├── utils/
│   │   ├── llm_factory.py           # LLM 工厂：单例 + 懒加载
│   │   └── llm_response.py          # LLM 响应解析工具
│   └── workflow/
│       └── review_workflow.py       # LangGraph 状态图（备选方案）
├── frontend/
│   ├── app.py                       # Streamlit 入口
│   └── components/chat.py           # 聊天界面：SSE 流式输出
└── docs/
    └── system-architecture.md       # 系统架构文档
```

---

> 文档版本：v1.0 | 生成时间：2026-07-16
