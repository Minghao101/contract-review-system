# 记忆架构总结

## 一、整体架构

项目设计了 4 层记忆，全部在用：

| 层级 | 模块 | 存储介质 | 用途 |
|------|------|----------|------|
| 对话上下文 | `ConversationContext` | 内存（Python对象） | 多轮对话的状态管理 |
| 长期记忆 | `LongTermMemory` | Qdrant 向量数据库 | 跨会话的审查历史持久化 |
| Agent私有记忆 | `AgentPrivateMemory` | 内存 | Agent 级缓存（增量分析结果缓存） |
| 共享记忆 | `SharedMemoryManager` | 内存 | Agent 间事件驱动协作的数据通道 |

---

## 二、ConversationContext（对话上下文）— 核心

### 文件位置
`src/agents/conversation_context.py`

### 数据结构

```
ConversationContext
├── _messages: deque[Message]          # 对话历史（用户+助手的消息记录）
├── _turns: list[TurnContext]          # 每轮对话的完整记录
│   └── TurnContext
│       ├── user_message: Message      # 用户消息
│       ├── assistant_message: Message # 助手回复
│       ├── intent: str                # 该轮意图
│       ├── intent_confidence: float   # 意图置信度
│       └── agent_results: dict        # 该轮执行的Agent结果
├── _current_turn: TurnContext         # 当前正在处理的轮次
├── _shared_data: dict                 # Agent间共享数据（合同文本等）
├── _intent_chain: list[str]           # 意图序列
├── _uploaded_files: list[dict]        # 上传文件记录
├── state: ConversationState           # 对话状态
└── _metadata: dict                    # 元数据（session_id, 创建时间等）
```

### 各字段职责

| 字段 | 职责 | 写入时机 | 读取时机 |
|------|------|----------|----------|
| `_messages` | 用户和助手的对话记录 | 每轮对话时 | 追问时构建上下文 |
| `_turns` | 每轮的Agent执行结果 | Agent执行完成后 | `get_all_results()` 收集 |
| `_shared_data` | Agent间传递的中间数据 | 合同上传、Agent间传递 | Agent执行时读取 |
| `_intent_chain` | 意图识别历史 | 每轮意图识别后 | 意图识别时读取上一轮意图 |

### `_shared_data` 只存这些（遗留机制）

```python
{
    "contract_text": "合同原文...",           # 合同文本
    "contract_filename": "劳动合同.txt",      # 文件名
    "parsed_result": {...},                   # Agent间传递（document_parser → risk_assessor）
}
```

**注意**：Agent 间的主要数据传递已迁移到 `SharedMemoryManager`（三层存储）。`_shared_data` 仅作为遗留兼容保留。

**不存** Agent 最终执行结果，Agent 结果存在 `_turns[*].agent_results` 中。

### 数据流

```
用户发送消息
    │
    ▼
ctx.add_user_message(text)          # → _messages
    │
    ▼
意图识别（注入 intent_context）      # → _intent_chain
    │
    ▼
执行 Agent
    │
    ├─→ ctx.set_agent_result(...)    # → _turns[current].agent_results
    │
    ▼
格式化回复
    │
    ▼
ctx.add_assistant_message(response) # → _messages
```

### 追问时的上下文构建

追问（`_answer_from_context`）只用两个字段：

```python
# 1. 合同内容
contract_text = ctx.get_contract_text()   # → _shared_data["contract_text"]

# 2. 对话历史
messages = ctx.get_messages()             # → _messages
```

LLM 收到的 prompt：
```
=== 合同内容 ===
甲方（用人单位）：XX科技有限公司...

=== 对话历史 ===
用户: 这个合同有什么风险？
助手: ⚠️ 风险评估完成 🔴 风险等级: HIGH...
用户: 第二条建议什么意思？

用户问题：第二条建议什么意思？
```

追问不需要读取 `_turns` 中的 Agent 原始结果，因为 `_messages` 中助手的回复已经包含了格式化的分析结果。

### 生命周期

```
新建对话 → ConversationContext(session_id=新UUID)
    │
    ▼
多轮对话 → 同一个 context，_messages 和 _turns 不断追加
    │
    ▼
用户点"新建对话" → 前端生成新 session_id → 后端创建新 context
    │
    ▼
重启后端服务 → _sessions 字典清空 → 所有 context 丢失
    │
    ▼
Runtime 生命周期: _runtimes[session_id] 保留跨请求，重启后清空
```

### 存储位置

```python
# ConversationManager 内部
self._sessions: Dict[str, ConversationContext] = {
    "abc-123": ConversationContext(...),   # 纯内存，重启即丢失
    "def-456": ConversationContext(...),
}
```

---

## 三、LongTermMemory（长期记忆）

### 文件位置
`src/memory/long_term_memory.py`

### 存储介质
Qdrant 向量数据库

### 记忆类型

| 类型 | 用途 | 写入时机 |
|------|------|----------|
| `review` | 合同审查历史 | 每次审查完成后自动保存 |
| `preference` | 用户偏好 | 手动保存 |
| `knowledge` | 知识积累 | 手动保存 |

### 数据结构（Qdrant payload）

```json
{
    "type": "review",
    "user_id": "default",
    "contract_name": "劳动合同范本.txt",
    "contract_summary": "甲方（用人单位）：XX科技有限公司...",
    "memory_text": "合同: 劳动合同范本.txt | 类型: labor | 风险: 工作时间违规, 违约金过高",
    "result_summary": {
        "risk_level": "high",
        "compliance_score": 72,
        "risks_count": 3,
        "violations_count": 1
    },
    "created_at": "2026-06-22T14:30:00"
}
```

### 使用场景

**写入**：`task_manager.py` 审查完成后自动保存
```python
memory = get_long_term_memory()
memory.save_review_memory(
    contract_name=contract_name,
    contract_text=contract_text,
    result=flat_result,
)
```

**读取**：前端查询历史记录
```python
# API: GET /api/v1/memory/recall?query=劳动合同&top_k=5
memory = get_long_term_memory()
results = memory.recall(query=query, memory_type="review", top_k=5)

# API: GET /api/v1/memory/history?top_k=10
results = memory.get_review_history(top_k=10)
```

---

## 四、AgentPrivateMemory（私有记忆）— 缓存层

### 文件位置
`src/memory/private_memory.py`

### 实际用途
每个 Agent 独立的记忆空间，当前主要用于**增量分析缓存**：
- `cache`: 缓存上次的完整分析结果，供增量修改时复用
- `context_window`: 上下文窗口（预留，支持压缩）
- `task_state`: 任务状态（预留）

### 初始化
`BaseAgent.bind_infrastructure()` 中自动创建：
```python
self._private_memory = AgentPrivateMemory(self.agent_id)
```

### 缓存使用场景（增量修改）

**写入缓存**：每次全量分析完成后
```python
# 在 RiskAssessmentAgent/ClauseAnalysisAgent/ComplianceCheckerAgent 的 process() 中
self._private_memory.set_cache("last_result", result)
```

**读取缓存**：增量修改时
```python
# Agent 检测到 modify_contract 意图
cached = self._private_memory.get_cache("last_result")
if cached:
    # 只重新分析修改后的条款，合并到 cached 结果
    return await self._incremental_analyze(updated_clause, cached)
else:
    # 无缓存（首次分析），走全量分析
    return await self._full_analyze(...)
```

### 缓存键

| 键名 | 值 | 用途 |
|------|-----|------|
| `{session_id}:last_result` | 完整分析结果 dict | 增量修改时复用，按会话隔离 |

缓存键通过 `_get_cache_key()` 生成，从共享内存读取 `session_id`：
```python
def _get_cache_key(self) -> str:
    session_id = self.read_shared("session_id", MemoryLayer.CONTEXT) or "default"
    return f"{session_id}:last_result"
```

这样不同会话的缓存互不干扰，同一会话内可复用上次分析结果。

---

## 五、SharedMemoryManager（共享记忆）— 事件驱动核心

### 文件位置
`src/memory/shared_memory.py`

### 实际用途
事件驱动架构的核心数据通道，Agent 间通过共享内存传递数据。

### 三层存储

| 层级 | MemoryLayer | 用途 | 写入方 | 读取方 |
|------|-------------|------|--------|--------|
| CONTEXT | `MemoryLayer.CONTEXT` | 原始输入（只读） | 调度器 | 所有 Agent |
| ANALYSIS | `MemoryLayer.ANALYSIS` | Agent 分析结果 | 各 Agent | 下游 Agent / 调度器 |
| DECISION | `MemoryLayer.DECISION` | 最终报告 | ReportGenerator | 调度器 |

### CONTEXT 层数据（调度器写入，Agent 只读）

| 键名 | 值 | 用途 |
|------|-----|------|
| `contract_text` | 合同原文 | 所有 Agent 的输入 |
| `contract_type` | 合同类型 | 合规检查等使用 |
| `intent_type` | 意图类型 | Agent 判断是否走增量分支 |
| `session_id` | 会话 ID | 事件发布时携带 |
| `user_message` | 用户原始消息 | 修改指令解析使用 |
| `_pending_count` | 待完成 Agent 数 | 聚合屏障计数器 |
| `_required_agents` | 需要执行的 Agent 列表 | 调度器按需执行 |

### ANALYSIS 层数据（各 Agent 写入，key = agent_id）

| 键名 | 写入方 | 值类型 |
|------|--------|--------|
| `document_parser` | DocumentParserAgent | DocumentParseResult |
| `risk_assessor` | RiskAssessmentAgent | RiskAssessmentResult |
| `clause_analyst` | ClauseAnalysisAgent | ClauseAnalysisResult |
| `compliance_checker` | ComplianceCheckerAgent | ComplianceCheckResult |
| `modify_instruction` | MultiTurnHandler | ModifyInstruction |
| `updated_clause` | DocumentParserAgent | 更新后的条款 |

### DECISION 层数据

| 键名 | 写入方 | 值类型 |
|------|--------|--------|
| `report_generator` | ReportGeneratorAgent | ReportResult |
| `risk_level` | ReportGeneratorAgent | str |

### Agent 读写模式

```python
# 读取
contract_text = self.read_shared("contract_text", MemoryLayer.CONTEXT)

# 写入（带 Schema 校验）
self.write_shared("risk_result", result, MemoryLayer.ANALYSIS)

# 写入（跳过校验，内部字段）
self.write_shared("_pending_count", 2, MemoryLayer.CONTEXT, validate=False)
```

### 初始化流程

```python
# MultiTurnHandler.__init__()
# 创建 RuntimeProxy / MessageBusProxy（Agent 绑定 proxy 而非具体实例）
self._sm_proxy = RuntimeProxy(lambda sid: self._runtimes.get(sid))
self._bus_proxy = MessageBusProxy(lambda sid: self._runtimes.get(sid))

# MultiTurnHandler.handle_message()
runtime = self._init_runtime(session_id, ...)       # 创建独立 SharedMemoryManager
token = _current_session_id.set(session_id)          # 设置 contextvar

for agent in self._agents.values():
    agent.bind_infrastructure(
        self._sm_proxy,          # proxy（非具体 SharedMemoryManager）
        self._bus_proxy,         # proxy（非具体 MessageBus）
        on_all_complete=self._make_on_complete_callback(runtime),
    )
# ... 执行完成 ...
_current_session_id.reset(token)                     # 释放 contextvar
```

---

## 六、完整数据流图

### 6.1 全量审查流程

```
用户: "全面审查这个合同"
    │
    ▼
MultiTurnHandler.handle_message()
    │
    ├─→ IntentRecognizer: "contract_review"
    │
    ├─→ _init_runtime()
    │     SharedMemoryManager 写入 CONTEXT 层:
    │       contract_text, contract_type, intent_type,
    │       _pending_count=3, _required_agents=[...]
    │
    ├─→ _current_session_id.set(session_id)  ← 设置 contextvar
    │
    ├─→ bind_infrastructure() → 所有 Agent
    │     每个 Agent 绑定: RuntimeProxy, MessageBusProxy, private_memory
    │     (proxy 通过 contextvar 自动路由到当前 session 的 runtime)
    │
    ├─→ _execute_full_review_chain()
    │     │
    │     ├─ Step 1: DocumentParserAgent
    │     │   read_shared("contract_text", CONTEXT)
    │     │   → LLM 解析 → write_shared("document_parser", ANALYSIS)
    │     │   → publish_event("document.parsed")
    │     │
    │     ├─ Step 2: 并行启动 3 个分析 Agent
    │     │   │
    │     │   ├─ RiskAssessmentAgent
    │     │   │   read_shared("contract_text", CONTEXT)
    │     │   │   → LLM 分析 → write_shared("risk_assessor", ANALYSIS)
    │     │   │   → _private_memory.set_cache("last_result", result)
    │     │   │   → decrement_pending_count() → 2
    │     │   │
    │     │   ├─ ClauseAnalysisAgent
    │     │   │   → write_shared("clause_analyst", ANALYSIS)
    │     │   │   → _private_memory.set_cache("last_result", result)
    │     │   │   → decrement_pending_count() → 1
    │     │   │
    │     │   └─ ComplianceCheckerAgent
    │     │       → write_shared("compliance_checker", ANALYSIS)
    │     │       → _private_memory.set_cache("last_result", result)
    │     │       → decrement_pending_count() → 0 ← 触发回调!
    │     │
    │     ├─→ _analysis_complete_event.set()  (聚合屏障归零)
    │     │
    │     └─ Step 3: ReportGeneratorAgent (被回调自动触发)
    │         read_shared("document_parser/risk_assessor/clause_analyst/compliance_checker", ANALYSIS)
    │         → write_shared("report_generator", DECISION)
    │         → publish_event("task.completed")
    │
    └─→ 收集结果 → 格式化回复
```

### 6.2 增量修改流程

```
用户: "把第三条的违约金从5%改成3%"
    │
    ▼
MultiTurnHandler.handle_message()
    │
    ├─→ IntentRecognizer: "modify_contract"
    │
    ├─→ _init_infrastructure() + 存储 user_message
    │
    ├─→ _execute_incremental_modify()
    │     │
    │     ├─ Step 1: _parse_modify_instruction()
    │     │   LLM Function Calling → ModifyInstruction
    │     │   {action: "replace", locate_type: "clause_number",
    │     │    locate_value: "第三条", old_content: "5%",
    │     │    new_content: "3%", confidence: 0.9}
    │     │
    │     ├─ Step 2: DocumentParserAgent
    │     │   read_shared("modify_instruction", ANALYSIS)
    │     │   → _locate_clause() 双重匹配定位
    │     │   → _replace_clause() 替换文本
    │     │   → write_shared("document_parser", ANALYSIS) 更新
    │     │   → write_shared("updated_clause", ANALYSIS) 通知下游
    │     │   → publish_event("clause.updated")
    │     │
    │     └─ Step 3: 并行增量分析
    │         │
    │         ├─ RiskAssessmentAgent
    │         │   检测到 modify_contract 意图
    │         │   → _private_memory.get_cache("last_result") 读缓存
    │         │   → _incremental_analyze() 只分析第三条
    │         │   → _merge_incremental_result() 合并到缓存
    │         │
    │         ├─ ClauseAnalysisAgent (同上)
    │         │
    │         └─ ComplianceCheckerAgent (同上)
    │
    └─→ 收集增量结果 → 格式化回复
```

### 6.3 追问流程

```
用户: "第二条建议什么意思？"
    │
    ▼
IntentRecognizer: "question_answer"
    │
    ▼
_answer_from_context()
    context = 合同内容(_shared_data["contract_text"])
            + 对话历史(_messages)
    → LLM 生成回答
```

---

## 七、架构修复记录

### 7.1 SharedMemory 生命周期问题

**问题**：每次请求创建新的 SharedMemoryManager，请求结束后 `_runtimes.pop()` 销毁。跨请求的中间数据（如 `updated_clause`、`modify_instruction`）丢失。

**修复**：移除 `_runtimes.pop()`，runtime 保留在 `_runtimes` 字典中，下次同 session 请求可复用。

```python
# 修复前（每次请求销毁）
self._runtimes.pop(session_id, None)

# 修复后（runtime 保留）
_current_session_id.reset(token)  # 只释放 contextvar，runtime 保留
```

### 7.2 Agent Singleton 并发绑定问题

**问题**：`bind_infrastructure()` 直接修改 singleton Agent 的 `self._shared_memory` 等实例属性。并发请求 B 会覆盖请求 A 的引用，导致数据错乱。

**修复**：引入 `RuntimeProxy` 和 `MessageBusProxy` 代理类。Agent 绑定 proxy 而非具体实例，proxy 通过 `contextvars.ContextVar` 在每次 `read`/`write` 时自动解析到当前 session 的 runtime。

```python
# RuntimeProxy 核心逻辑
_current_session_id: contextvars.ContextVar[str] = ContextVar('current_session_id', default='default')

class RuntimeProxy:
    def _get_sm(self):
        session_id = _current_session_id.get()       # 从 contextvar 获取当前 session
        runtime = self._get_runtime(session_id)      # 从 _runtimes 字典查找
        return runtime.shared_memory if runtime else None

    def read(self, agent_id, key, layer):
        sm = self._get_sm()
        return sm.read(agent_id, key, layer) if sm else None

    def write(self, agent_id, key, value, layer, validate=True):
        sm = self._get_sm()
        return sm.write(agent_id, key, value, layer, validate=validate) if sm else 0
```

**请求隔离流程**：
```
请求 A (session=abc)
    │
    ├─ token_a = _current_session_id.set("abc")
    │   Agent.read_shared() → proxy._get_sm() → _runtimes["abc"].shared_memory
    │
    └─ _current_session_id.reset(token_a)

请求 B (session=def)  ← 与 A 并发
    │
    ├─ token_b = _current_session_id.set("def")
    │   Agent.read_shared() → proxy._get_sm() → _runtimes["def"].shared_memory
    │
    └─ _current_session_id.reset(token_b)
```

### 7.3 AgentPrivateMemory 初始化时机

**问题**：`bind_infrastructure()` 每次调用都创建新的 `AgentPrivateMemory`，新请求覆盖旧的缓存引用。

**修复**：只在第一次绑定时创建，后续请求复用同一个 `_private_memory` 实例（singleton Agent 跨请求共享缓存）。

```python
# 修复前（每次覆盖）
self._private_memory = AgentPrivateMemory(self.agent_id)

# 修复后（只创建一次）
if self._private_memory is None:
    self._private_memory = AgentPrivateMemory(self.agent_id)
```

---

## 八、关键代码文件索引

| 文件 | 职责 |
|------|------|
| `src/agents/conversation_context.py` | 对话上下文管理（消息、轮次、Agent结果、共享数据） |
| `src/agents/multi_turn_handler.py` | 多轮对话处理（意图识别→Agent执行→结果存储→追问回答→增量修改调度） |
| `src/agents/intent_recognizer.py` | 意图识别（LLM Function Calling，支持 9 种意图） |
| `src/agents/base_agent.py` | Agent 基类（共享内存绑定、聚合屏障、事件发布） |
| `src/agents/shared_data_schemas.py` | Agent 间数据 Schema（Pydantic 校验，含 ModifyInstruction） |
| `src/agents/business_events.py` | 业务事件常量（7 种事件类型） |
| `src/agents/document_parser_agent.py` | 文档解析 + 增量修改（条款定位、替换、插入） |
| `src/agents/risk_assessment_agent.py` | 风险评估 + 增量分析（缓存复用、结果合并） |
| `src/agents/clause_analysis_agent.py` | 条款分析 + 增量分析 |
| `src/agents/compliance_checker_agent.py` | 合规检查 + 增量分析 |
| `src/agents/report_generator_agent.py` | 报告生成（聚合屏障触发） |
| `src/memory/long_term_memory.py` | 长期记忆（Qdrant 向量存储） |
| `src/memory/private_memory.py` | Agent 私有记忆（增量分析缓存） |
| `src/memory/shared_memory.py` | 共享记忆管理器（事件驱动核心数据通道） |
| `src/memory/memory_layer.py` | 记忆层次枚举（CONTEXT/ANALYSIS/DECISION） |
| `src/api/task_manager.py` | 任务管理（调用handler + 保存长期记忆） |
| `src/api/routes.py` | API路由（/review/stream, /memory/recall 等） |
| `frontend/components/chat.py` | 前端聊天界面（session_state管理） |
