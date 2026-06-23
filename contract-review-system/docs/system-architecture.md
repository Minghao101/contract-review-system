# 智能合同审查系统 — 架构与代码逻辑说明

> LangChain + 多 Agent + LLM Function Calling + 事件驱动协作

---

## 1. LangChain 生态

本项目使用 LangChain 生态的核心组件构建 AI Agent 应用。

| 包 | 用途 |
|---|------|
| `langchain-core` | `BaseLLM` 抽象基类、`SystemMessage/HumanMessage` 消息格式化、`with_structured_output()` 结构化输出 |
| `langchain-anthropic` | `ChatAnthropic` — 当前使用的 LLM 接口，通过 MIMO 代理调用 |
| `langchain-openai` | `ChatOpenAI` — 备选方案，兼容任何 OpenAI 格式 API |
| `langchain-community` | `Ollama` — 本地模型回退方案 |

**本项目怎么用 LangChain？**

项目**没有**用 LangChain 的 Agent/Chain/AgentExecutor 高层抽象，而是：
1. 用 `ChatAnthropic` 作为 LLM 调用层
2. 用 `SystemMessage + HumanMessage` 构建 prompt
3. 用 `llm.ainvoke(messages)` 异步调用
4. 用 `llm.with_structured_output()` 做意图识别（Function Calling）
5. Agent 间协作通过共享内存 + 消息总线事件驱动

---

## 2. 系统全景架构（阶段1：弱中心化）

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
│  ANALYSIS 层         │
│  ├─ parsed_result    │           ▲
│  ├─ risk_result      │           │ 订阅事件
│  ├─ clause_result    │           │
│  └─ compliance_result│           │
│                      │  ┌────────┴───────────────────┐
│  DECISION 层         │  │       Agent Layer            │
│  ├─ final_report     │  │  DocumentParser               │
│  └─ risk_level       │  │  ClauseAnalysis               │
└──────────────────────┘  │  RiskAssessment               │
                          │  ComplianceChecker            │
                          │  ReportGenerator              │
                          │  (各自订阅事件→读共享内存→      │
                          │   执行→写共享内存→发布事件)     │
                          └──────────────────────────────┘
```

---

## 3. 事件驱动执行链路

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
    ReportGeneratorAgent（所有分析完成后触发）
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

---

## 4. LLM 工厂 — llm_factory.py

统一管理 LLM 实例，所有 Agent 通过 `get_llm()` 获取。

```python
class LLMFactory:
    def __init__(self):
        self._llm = None  # 单例缓存

    def create_llm(self, provider=None):
        if provider == "anthropic":
            return ChatAnthropic(
                model="mimo-v2.5",
                base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
                temperature=0.3, max_tokens=10000,
            )

    def get_llm(self):
        if self._llm is None:
            self._llm = self.create_llm()  # 懒加载 + 单例
        return self._llm
```

---

## 5. BaseAgent 基类 — base_agent.py

所有 Agent 的父类，集成共享内存和消息总线。

```python
class BaseAgent(ABC):
    def __init__(self, agent_id, name, role, llm=None):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.llm = llm or get_llm()
        # 阶段1：基础设施
        self._shared_memory = None
        self._message_bus = None
        self._private_memory = None

    def bind_infrastructure(self, shared_memory, message_bus):
        """绑定共享内存和消息总线"""
        self._shared_memory = shared_memory
        self._message_bus = message_bus
        self._private_memory = AgentPrivateMemory(self.agent_id)

    def read_shared(self, key, layer):
        return self._shared_memory.read(self.agent_id, key, layer)

    def write_shared(self, key, value, layer):
        return self._shared_memory.write(self.agent_id, key, value, layer)

    def publish_event(self, event_type, data):
        msg = AgentMessage(self.agent_id, "*", MessageType.NOTIFICATION,
                           {"event": event_type, **data})
        self._message_bus.publish(msg)

    @abstractmethod
    async def process(self, task: Dict) -> Dict:
        pass
```

**设计要点**：Agent 不再通过 `task` 参数接收数据，统一从共享内存读取依赖、写入结果。

---

## 6. IntentRecognizer — 意图识别

基于 LLM Function Calling 的意图分类，零关键词匹配。

```python
class IntentResult(BaseModel):
    """用于 Function Calling 的结构化输出"""
    intent: IntentType
    confidence: float
    entities: Dict
    reasoning: str

async def _recognize_by_function_calling(self, text, context):
    structured_llm = self.llm.with_structured_output(IntentResult)
    messages = [HumanMessage(content="你是一个意图识别专家...\n用户输入: {text}")]
    result = await structured_llm.ainvoke(messages)
    return Intent(type=result.intent, confidence=result.confidence, ...)
```

### 意图路由表

| 意图类型 | 判断规则 | 执行方式 | 需要合同 |
|---------|---------|---------|---------|
| `contract_review` | 明确要求"完整/全面/整体审查" | 完整事件链（4 Agent） | 是 |
| `risk_assessment` | 提到"风险" | 单 Agent 执行 | 是 |
| `compliance_check` | 提到"合规/合法" | 单 Agent 执行 | 是 |
| `clause_analysis` | 提到"条款" | 单 Agent 执行 | 是 |
| `report_generation` | 要求生成/导出报告 | 单 Agent 执行 | 否 |
| `question_answer` | 追问、提问（默认） | LLM 直接回答 | 否 |
| `greeting` | 打招呼 | 直接回复 | 否 |

---

## 7. MultiTurnHandler — 启动协调者

阶段1改造后，调度器退化为启动协调者，只保留三个核心职责：

### 职责

1. **初始化共享内存**：写入合同文本、类型等 CONTEXT 层数据
2. **按需启动 Agent**：根据意图决定需要哪些 Agent，发布对应事件
3. **等待结果**：通过 `asyncio.Event` + 全局超时等待任务完成

### 关键机制

#### 聚合屏障（Aggregation Barrier）

解决「ReportGenerator 何时触发」的问题。共享内存 CONTEXT 层维护 `_pending_count` 计数器：

```python
# 初始化时写入
_pending_count = len(required_agents) - 1  # 排除 DocumentParser（它是第一步）
self._shared_memory.write("coordinator", "_pending_count", _pending_count, MemoryLayer.CONTEXT, validate=False)
```

每个分析 Agent（Risk/Clause/Compliance）执行完毕后递减计数器。当计数器归零时，触发 ReportGenerator：

```python
# Agent 完成后递减
pending = self._shared_memory.read("system", "_pending_count", MemoryLayer.CONTEXT)
if pending is not None and pending > 0:
    self._shared_memory.write("system", "_pending_count", pending - 1, MemoryLayer.CONTEXT, validate=False)
    if pending - 1 == 0:
        # 所有分析完成，触发 ReportGenerator
        self.publish_event(BusinessEvent.TASK_COMPLETED, {...})
```

#### 按需调度（Required Agents）

解决「单意图资源浪费」的问题。不同意图只需执行不同的 Agent 子集：

```python
INTENT_REQUIRED_AGENTS = {
    IntentType.CONTRACT_REVIEW: ["document_parser", "risk_assessor", "clause_analyst", "compliance_checker", "report_generator"],
    IntentType.RISK_ASSESSMENT: ["document_parser", "risk_assessor"],
    IntentType.CLAUSE_ANALYSIS: ["document_parser", "clause_analyst"],
    IntentType.COMPLIANCE_CHECK: ["document_parser", "compliance_checker"],
    IntentType.REPORT_GENERATION: ["report_generator"],
}
```

调度器在初始化时将 `_required_agents` 写入 CONTEXT 层，每个 Agent 执行前检查自己是否在列表中。

#### asyncio.Event 等待机制

解决「调度器如何等待结果」的问题。替代轮询，使用事件驱动的精确等待：

```python
self._completion_event = asyncio.Event()

# 等待 task.completed 事件（带全局超时）
await asyncio.wait_for(self._completion_event.wait(), timeout=_TASK_TIMEOUT)  # 180s
```

ReportGenerator 发布 `task.completed` 事件时，通过回调设置 `self._completion_event.set()`，调度器立即收到通知。

#### 全局超时熔断

防止 Agent 卡死导致整个流程挂起：

```python
_TASK_TIMEOUT = 180  # 秒

result = await asyncio.wait_for(
    self._execute_event_driven(session_id),
    timeout=_TASK_TIMEOUT
)
```

超时后收集已有结果，降级返回部分审查结论。

### 执行流程

```
用户发送消息
    │
    ▼
ctx.add_user_message()
    │
    ▼
IntentRecognizer.recognize()
    │
    ├─ greeting/question_answer/unknown → 直接回复（不变）
    │
    └─ contract_review/risk/clause/compliance/report → 事件驱动
        │
        ▼
    _init_infrastructure()
    │   ├── SharedMemoryManager(contract_id=session_id)
    │   ├── 写入 CONTEXT 层: contract_text, contract_type, _required_agents, _pending_count
    │   └── MessageBus()
        │
        ▼
    agent.bind_infrastructure(shared_memory, message_bus)
    │
        ▼
    _execute_event_driven() [asyncio.wait_for(timeout=180s)]
    │   ├── _execute_by_intent() → 只启动 required_agents 中的 Agent
    │   ├── document_parser → document.parsed
    │   ├── risk/clause/compliance → 并行执行，完成后递减 _pending_count
    │   ├── _pending_count == 0 → task.completed → ReportGenerator
    │   └── _completion_event.set() → 调度器收到通知
        │
        ▼
    _collect_results_from_memory() + _format_response()
```

### 追问处理

追问（`_answer_from_context`）仍使用合同文本 + 对话历史构建上下文，让 LLM 直接回答。

---

## 8. DocumentParserAgent — 文档解析

LLM 驱动的合同结构化信息提取，支持长文本 Map-Reduce。

```python
async def process(self, task):
    # 从共享内存读取（事件驱动模式）
    contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT)
    contract_type = self.read_shared("contract_type", MemoryLayer.CONTEXT)

    # 业务逻辑不变
    if len(contract_text) > self.chunk_size:
        result = await self._map_reduce_extract(contract_text, contract_type)
    else:
        result = await self._llm_extract_all(contract_text, contract_type)

    # 写入共享内存 + 发布事件
    self.write_shared("parsed_result", result, MemoryLayer.ANALYSIS)
    self.publish_event(BusinessEvent.DOCUMENT_PARSED, {"session_id": ...})
    return result
```

---

## 9. RiskAssessmentAgent — 风险评估

纯 LLM 风险识别 + 量化评分 + 缓解建议。

```python
async def process(self, task):
    contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT)
    parsed_result = self.read_shared("parsed_result", MemoryLayer.ANALYSIS)

    result = await self._assess_with_llm(contract_text, contract_type)
    result["risk_quantification"] = self.quantify_risk(result.get("risks", []))
    result["mitigation_plan"] = self.suggest_mitigation(result.get("risks", []))

    self.write_shared("risk_result", result, MemoryLayer.ANALYSIS)
    self.publish_event(BusinessEvent.RISK_ANALYZED, {"session_id": ...})
    return result
```

**风险量化**：severity(high=3, medium=2, low=1) × category 权重 → 归一化到 0-100 分。

---

## 10. ClauseAnalysisAgent — 条款分析

纯 LLM 条款语义分析 + 完整性评估。

单次 LLM 调用完成：completeness（完整性）、ambiguous_clauses（模糊条款）、rights_obligations（权利义务平衡）、issues（问题列表）。

---

## 11. ComplianceCheckerAgent — 合规检查

LLM 驱动的法规合规检查。

```python
class ComplianceCheckerAgent(BaseAgent):
    REQUIRED_CLAUSES = {
        "sales": ["标的物", "价款", "交付", "验收", "违约责任", "争议解决"],
        "service": ["服务内容", "服务期限", "服务费用", "验收标准", "违约责任", "保密"],
        "labor": ["工作内容", "劳动报酬", "工作时间", "社会保险", "劳动保护", "解除条件"],
    }
```

**设计决策**：`REQUIRED_CLAUSES` 仅作为 LLM prompt 上下文参考，不用于关键词匹配。

---

## 12. ReportGeneratorAgent — 报告生成

汇总前序 Agent 结果，LLM 生成结构化审查报告。

```python
async def process(self, task):
    # 从共享内存读取所有分析结果
    parsed = self.read_shared("parsed_result", MemoryLayer.ANALYSIS)
    risk = self.read_shared("risk_result", MemoryLayer.ANALYSIS)
    clause = self.read_shared("clause_result", MemoryLayer.ANALYSIS)
    compliance = self.read_shared("compliance_result", MemoryLayer.ANALYSIS)

    # 业务逻辑不变
    result = await self._generate_with_llm(previous_results)

    # 写入 DECISION 层
    self.write_shared("final_report", result, MemoryLayer.DECISION)
    self.publish_event(BusinessEvent.TASK_COMPLETED, {"session_id": ...})
    return result
```

---

## 13. 三层共享内存 — SharedMemoryManager

替代旧的 `_shared_data`，作为 Agent 间唯一的数据交换中枢。

| 层级 | 用途 | 数据 | 写入者 | 读取者 |
|------|------|------|--------|--------|
| CONTEXT | 合同上下文（只读） | contract_text, contract_type, review_focus, _required_agents, _pending_count | 调度器（一次性写入） | 所有 Agent |
| ANALYSIS | 分析结果 | parsed_result, risk_result, clause_result, compliance_result | 各 Agent 自主写入 | ReportGenerator |
| DECISION | 最终交付物 | final_report, risk_level | ReportGenerator | 调度器、前端 |

**设计要点**：
- 线程安全（内置 Lock）
- 版本控制（每次写入自增版本号）
- 变更通知（观察者模式）
- **Schema 校验**：核心业务数据（parsed_result, risk_result 等）写入时自动校验 Pydantic Schema，非核心数据（_pending_count 等）跳过校验

### Schema 校验机制

`write()` 方法新增 `validate` 参数（默认 True）。写入时通过延迟加载的 `validate_shared_data(key, value)` 校验数据是否符合 Schema 定义：

```python
def write(self, agent_id, key, value, layer, validate=True) -> int:
    if validate:
        validator = _get_schema_validator()
        if not validator(key, value):
            logger.warning(f"共享数据校验失败: key={key}")
            return -1  # 校验失败，拒绝写入
    # ... 正常写入
```

内部控制字段（如 `_pending_count`, `_required_agents`）使用 `validate=False` 跳过校验。

---

## 14. 数据契约 — shared_data_schemas.py

所有 Agent 间通过共享内存传递的核心业务数据都有明确的 Pydantic Schema，杜绝魔法字符串和运行时取值错误。

### Schema 注册表

```python
SHARED_DATA_SCHEMAS = {
    "parsed_result": DocumentParseResult,      # DocumentParser → ANALYSIS
    "risk_result": RiskAssessmentResult,       # RiskAssessor → ANALYSIS
    "clause_result": ClauseAnalysisResult,     # ClauseAnalyst → ANALYSIS
    "compliance_result": ComplianceCheckResult, # ComplianceChecker → ANALYSIS
    "final_report": ReportResult,              # ReportGenerator → DECISION
}
```

### 校验规则

| Schema | 关键字段 | 校验点 |
|--------|---------|--------|
| `DocumentParseResult` | document_info, sections, dates, amounts, parties | 结构完整性 |
| `RiskAssessmentResult` | risk_level (low/medium/high/critical), risks, recommendations | 枚举值校验 |
| `ClauseAnalysisResult` | sections, analysis, missing_clauses, issues | 类型安全 |
| `ComplianceCheckResult` | compliance_status, score (0-100), compliance_violations | 范围校验 |
| `ReportResult` | report, summary, visualization, generated_at | 结构完整性 |

### 降级策略

- 非注册 key（如 `_pending_count`）：直接通过，不校验
- 校验失败：`write()` 返回 -1，数据不写入，日志记录 WARNING
- Schema 类导入失败：`validate_shared_data` 降级为始终返回 True

---

## 15. 容错机制 — Fault Tolerance

三层容错设计，确保单点故障不会导致整个审查流程卡死。

### 第一层：Agent 级 try/finally

每个 Agent 的 `process()` 方法用 `try/finally` 包裹，保证：
- **正常路径**：写入共享内存 + 发布事件 + `set_running(False)`
- **异常路径**：记录错误 + 写入错误状态到共享内存 + 发布事件（携带错误信息）+ `set_running(False)`
- **无论成功失败，事件必须发布**，下游可以做降级处理

```python
async def process(self, task):
    self.set_running(True)
    try:
        result = await self._core_logic()
        self.write_shared(key, result, MemoryLayer.ANALYSIS)
        self.publish_event(BusinessEvent.XXX_ANALYZED, {"session_id": ...})
        return result
    except Exception as e:
        error_result = {"error": str(e), ...}
        self.write_shared(key, error_result, MemoryLayer.ANALYSIS)
        self.publish_event(BusinessEvent.XXX_ANALYZED, {"session_id": ...})
        return error_result
    finally:
        self.set_running(False)
```

### 第二层：调度器级 asyncio.wait_for

全局超时熔断，防止 Agent 卡死导致整个流程挂起：

```python
_TASK_TIMEOUT = 180  # 秒

result = await asyncio.wait_for(
    self._execute_event_driven(session_id),
    timeout=_TASK_TIMEOUT
)
```

超时后收集已有结果，降级返回部分审查结论。

### 第三层：部分失败降级

`_execute_full_review_chain()` 使用 `asyncio.gather(return_exceptions=True)` 并行执行分析 Agent。单个 Agent 失败不影响其他 Agent：

```python
results = await asyncio.gather(
    self._agents["risk_assessor"].process(task),
    self._agents["clause_analyst"].process(task),
    self._agents["compliance_checker"].process(task),
    return_exceptions=True
)
```

失败的 Agent 结果标记为 `{"status": "failed", "error": str(e)}`，ReportGenerator 会基于已有结果生成降级报告。

### 故障场景与处理

| 故障场景 | 处理方式 | 用户感知 |
|---------|---------|---------|
| Agent LLM 调用超时 | try/except 捕获，返回 error_result | 该维度分析缺失，其他维度正常 |
| Agent 进程卡死 | 全局超时 180s 熔断 | 返回已有的部分结果 |
| 共享内存写入失败 | write() 返回 -1，日志记录 | Agent 重试或降级 |
| 事件丢失（Agent 未发布事件） | 聚合屏障超时未归零 → 触发 ReportGenerator | 基于已有结果生成报告 |
| ReportGenerator 失败 | 返回基础报告（_generate_basic_report） | 简版报告 |

---

## 16. 消息总线 — MessageBus

复用 `src/agents/communication.py`，Agent 间事件驱动通信。

| 事件 | 发布者 | 订阅者 | 含义 |
|------|--------|--------|------|
| `task.created` | MultiTurnHandler | DocumentParser | 新任务创建 |
| `document.parsed` | DocumentParser | Risk/Clause/Compliance | 文档解析完成 |
| `risk.analyzed` | RiskAssessor | ReportGenerator | 风险评估完成 |
| `clause.analyzed` | ClauseAnalyst | ReportGenerator | 条款分析完成 |
| `compliance.checked` | ComplianceChecker | ReportGenerator | 合规检查完成 |
| `task.completed` | ReportGenerator | MultiTurnHandler | 所有分析完成 |

---

## 17. 四层记忆系统

| 层级 | 模块 | 存储介质 | 状态 |
|------|------|----------|------|
| 对话上下文 | `ConversationContext` | 内存 | **在用** |
| 长期记忆 | `LongTermMemory` | Qdrant | **在用** |
| Agent私有记忆 | `AgentPrivateMemory` | 内存 | **已激活**（阶段1） |
| 共享记忆 | `SharedMemoryManager` | 内存 | **已激活**（阶段1） |

### AgentPrivateMemory

每个 Agent 独立的记忆空间：
- `context_window`: 上下文窗口（deque，支持压缩）
- `compressed_summary`: 压缩后的摘要
- `task_state`: 执行状态（未开始/执行中/成功/失败）
- `cache`: 中间计算缓存（支持 TTL 过期）

---

## 18. REST API 接口

| 方法 | 路径 | 说明 | 处理方式 |
|------|------|------|---------|
| POST | /api/v1/review | 提交合同审查 | 异步 (RabbitMQ) |
| POST | /api/v1/review/sync | 同步合同审查 | 直接处理返回 |
| POST | /api/v1/review/stream | 流式合同审查 | 处理后返回文本 |
| GET | /api/v1/tasks/{id} | 查询任务状态 | 文件持久化 |
| GET | /api/v1/tasks | 列出任务 | 支持状态过滤 |
| POST | /api/v1/upload | 上传文件审查 | PDF/DOCX/TXT |
| POST | /api/v1/upload/sync | 上传同步审查 | 直接返回结果 |
| GET | /api/v1/memory/recall | 查询历史记忆 | Qdrant 检索 |
| GET | /api/v1/memory/history | 审查历史 | Qdrant 检索 |
| GET | /health | 健康检查 | — |

---

## 19. 项目文件结构

```
contract-review-system/
├── config/
│   └── settings.py              # 全局配置：LLM/Qdrant/Embedding/RabbitMQ
├── src/
│   ├── agents/
│   │   ├── base_agent.py        # Agent 基类：bind_infrastructure + read/write_shared
│   │   ├── business_events.py   # ★新增★ 标准业务事件常量
│   │   ├── shared_data_schemas.py # ★新增★ Pydantic Schema：共享数据契约
│   │   ├── communication.py     # MessageBus 事件总线（增强版）
│   │   ├── langchain_agent.py   # LangChain 包装器：achat() 异步 LLM 调用
│   │   ├── multi_turn_handler.py # ★核心★ 启动协调者：初始化→发布事件→等待结果
│   │   ├── intent_recognizer.py  # 意图识别：LLM Function Calling
│   │   ├── conversation_context.py # 会话上下文：消息+轮次+Agent结果
│   │   ├── document_parser_agent.py # 共享内存读写 + 事件发布
│   │   ├── clause_analysis_agent.py  # 共享内存读写 + 事件发布
│   │   ├── risk_assessment_agent.py  # 共享内存读写 + 事件发布
│   │   ├── compliance_checker_agent.py # 共享内存读写 + 事件发布
│   │   ├── report_generator_agent.py  # 共享内存读写 + 事件发布
│   │   └── coordinator_agent.py    # 简化版：仅处理问候/未知意图
│   ├── api/
│   │   ├── main.py               # FastAPI 入口 + CORS
│   │   ├── routes.py             # API 路由：review/stream/upload/memory
│   │   ├── task_manager.py       # 任务管理：MultiTurnHandler + 持久化
│   │   └── document_parser.py    # 文件解析：PDF/DOCX/TXT → 文本
│   ├── services/
│   │   └── vector_store.py       # Qdrant：bge-m3 Embedding + 向量检索
│   ├── memory/
│   │   ├── long_term_memory.py   # 长期记忆：审查历史 → Qdrant
│   │   ├── shared_memory.py      # ★已激活★ 共享内存：三层数据交换中枢
│   │   ├── private_memory.py     # ★已激活★ Agent 私有记忆
│   │   └── memory_layer.py       # 记忆层次枚举（CONTEXT/ANALYSIS/DECISION）
│   ├── skills/
│   │   ├── risk/risk_identifier.py     # LLM 风险识别
│   │   ├── legal/regulation_checker.py # LLM 法规检查
│   │   ├── legal/clause_parser.py      # LLM 条款类型识别
│   │   └── legal/case_retriever.py     # LLM 案例相关性评分
│   ├── tools/
│   │   └── langchain_tools.py    # LangChain @tool 封装
│   └── utils/
│       ├── llm_factory.py        # LLM 工厂：单例 + 懒加载
│       └── llm_response.py       # extract_llm_content() + parse_json_from_llm()
├── frontend/
│   ├── app.py                    # Streamlit 入口
│   └── components/chat.py        # 聊天界面：session_state + 流式输出
├── tests/
└── scripts/
    └── init_vector_db.py         # 初始化 Qdrant 集合
```

---

## 20. 阶段1改造要点

### 设计约束

- **新增 Agent 只需**：订阅对应事件 + 读写共享内存，无需修改调度器核心代码
- **并行执行**：从「调度器手动 gather」变为「事件自动触发」，天然支持异步并发
- **现有闲置模块全部盘活**：SharedMemoryManager、AgentPrivateMemory、MessageBus
- **对外 API 接口完全兼容**，业务无感知

### 5 项关键设计增强

| # | 问题 | 解决方案 | 实现位置 |
|---|------|---------|---------|
| 1 | ReportGenerator 不知道上游何时完成 | 共享内存聚合屏障（`_pending_count` 计数器） | MultiTurnHandler + 各分析 Agent |
| 2 | 单意图触发全部 Agent，资源浪费 | `INTENT_REQUIRED_AGENTS` 按需调度 | MultiTurnHandler |
| 3 | 共享内存无数据契约，运行时取值错误 | Pydantic Schema 校验（`shared_data_schemas.py`） | SharedMemoryManager.write() |
| 4 | 调度器不知道如何等待结果 | `asyncio.Event` + 全局超时 `_TASK_TIMEOUT=180s` | MultiTurnHandler |
| 5 | Agent 失败导致静默阻塞，零容错 | try/finally + 事件必发 + 降级执行 | 各 Agent + MultiTurnHandler |

### 数据流对比

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

### 改造前 vs 改造后：核心优势对比

#### 1. 调度器职责

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **调度器角色** | 全知全能的指挥官 | 启动协调者 |
| **Agent 编排** | 手动 `asyncio.gather()` + 手动调用 ReportGenerator | Agent 自主协作，聚合屏障自动触发 |
| **新增 Agent** | 必须修改路由表 + `_prepare_agent_input()` | 只需订阅事件 + 读写共享内存 |

#### 2. 数据传递

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **数据来源** | 调度器手动构造 `task_context` 传给每个 Agent | Agent 自己从共享内存读取 |
| **数据重复** | 每个 Agent 都收到完整的 `task_context`（包含不需要的字段） | Agent 只读取需要的字段 |
| **调度器耦合** | 调度器必须知道每个 Agent 需要什么字段 | 调度器只写 CONTEXT 层，Agent 自主决定读什么 |

#### 3. 容错能力

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **Agent 异常** | 向上传播，可能导致整个链路崩溃 | try/finally 兜底，降级为错误结果 |
| **部分失败** | 一个 Agent 失败 → 整个 gather 可能失败 | 单点故障不影响其他 Agent |
| **全局超时** | 无 | `_TASK_TIMEOUT=180s` 熔断 |
| **事件丢失** | 无处理 | 聚合屏障超时降级 |

#### 4. 并行执行

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **并行方式** | 调度器手动 `asyncio.gather()` | Agent 自主响应事件，并行执行 |
| **触发机制** | 调度器决定何时并行 | 事件驱动，天然支持并行 |
| **同步点** | 调度器用 `gather()` 等待所有 Agent | 聚合屏障自动等待 |

#### 5. 可扩展性

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **新增 Agent** | 修改路由表 + `_prepare_agent_input()` + 调度器逻辑 | 只需 Agent 订阅事件 + 读写共享内存 |
| **新增意图** | 修改路由表 + 调度器逻辑 | 只需在 `INTENT_REQUIRED_AGENTS` 添加映射 |
| **Agent 间协作** | 全部通过调度器中转 | Agent 通过共享内存直接交换数据 |

#### 6. 数据契约

| 维度 | 改造前 | 改造后 |
|------|-------|-------|
| **数据校验** | 无（魔法字符串取值） | Pydantic Schema 校验 |
| **数据层次** | 扁平 dict | CONTEXT / ANALYSIS / DECISION 三层 |
| **版本控制** | 无 | 每次写入自增版本号 |

### 实际收益

| 收益 | 说明 |
|------|------|
| **省掉一次 LLM 调用** | 原来 CoordinatorAgent 用 LLM 规划执行计划，现在用静态列表直接确定 |
| **调度器不再需要知道 Agent 细节** | Agent 自己决定读什么数据、写什么结果 |
| **单点故障不影响整体** | 某个 Agent 崩溃，其他 Agent 继续执行 |
| **更易测试** | 每个 Agent 可以独立测试，不需要模拟整个调度器 |
| **更易扩展** | 新增 Agent 只需实现 `process()` 方法，不需要修改调度器 |

---

> 文档版本：v5.1 | 最后更新：2026-06-23
