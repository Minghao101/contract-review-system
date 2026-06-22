# 记忆架构总结

## 一、整体架构

项目设计了 4 层记忆，但实际在用的只有 2 层：

| 层级 | 模块 | 存储介质 | 是否在用 | 用途 |
|------|------|----------|----------|------|
| 对话上下文 | `ConversationContext` | 内存（Python对象） | **在用** | 多轮对话的状态管理 |
| 长期记忆 | `LongTermMemory` | Qdrant 向量数据库 | **在用** | 跨会话的审查历史持久化 |
| Agent私有记忆 | `AgentPrivateMemory` | 内存 | **未使用** | 设计了但未接入 |
| 共享记忆 | `SharedMemoryManager` | 内存 | **未使用** | 设计了但未接入 |

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

### `_shared_data` 只存这些

```python
{
    "contract_text": "合同原文...",           # 合同文本
    "contract_filename": "劳动合同.txt",      # 文件名
    "parsed_result": {...},                   # Agent间传递（document_parser → risk_assessor）
    "risk_result": {...},                     # Agent间传递（risk_assessor → clause_analyst）
}
```

**不存** Agent 最终执行结果（`result_*` 已移除），Agent 结果存在 `_turns[*].agent_results` 中。

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

## 四、AgentPrivateMemory（私有记忆）— 未使用

### 文件位置
`src/memory/private_memory.py`

### 设计用途
每个 Agent 独立的记忆空间，包含：
- `context_window`: 上下文窗口（deque，支持压缩）
- `compressed_summary`: 压缩后的摘要
- `task_state`: 任务状态
- `cache`: 缓存（支持 TTL 过期）

### 实际状态
定义了但未被任何 Agent 或 Handler 实例化使用。

---

## 五、SharedMemoryManager（共享记忆）— 未使用

### 文件位置
`src/memory/shared_memory.py`

### 设计用途
Agent 间共享记忆，支持：
- 分层存储（CONTEXT / ANALYSIS / DECISION）
- 版本控制
- 读写锁（线程安全）
- 变更通知（观察者模式）

### 实际状态
定义了但未被使用。Agent 间的数据传递目前通过 `ConversationContext._shared_data` 实现。

---

## 六、完整数据流图

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Streamlit)                    │
│                                                       │
│  st.session_state["messages"] = [                     │
│    {role: "user", content: "..."},                    │
│    {role: "assistant", content: "..."},               │
│  ]                                                    │
│  st.session_state["session_id"] = "abc-123"           │
└──────────────────────┬──────────────────────────────┘
                       │ POST /api/v1/review/stream
                       │ {contract_text, session_id, review_focus}
                       ▼
┌─────────────────────────────────────────────────────┐
│              task_manager.process_sync()               │
│                                                       │
│  1. 调用 multi_turn_handler.handle_message()          │
│  2. 扁平化结果 _flatten_agent_results()               │
│  3. 保存到 LongTermMemory (Qdrant)                    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│          multi_turn_handler.handle_message()           │
│                                                       │
│  ctx = conversation_manager.get_or_create(session_id) │
│                                                       │
│  ┌─ ConversationContext ─────────────────────────┐   │
│  │                                                │   │
│  │  _messages: [用户消息, 助手回复, ...]           │   │
│  │  _turns: [                                       │   │
│  │    TurnContext(intent, agent_results={...}),     │   │
│  │    TurnContext(intent, agent_results={...}),     │   │
│  │  ]                                               │   │
│  │  _shared_data: {                                 │   │
│  │    "contract_text": "...",                       │   │
│  │    "parsed_result": {...},  ← Agent间传递        │   │
│  │  }                                               │   │
│  │  _intent_chain: ["risk_assessment", ...]         │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  追问时：                                              │
│    context = 合同内容(_shared_data)                     │
│            + 对话历史(_messages)                        │
│    → 发给 LLM 生成回答                                 │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              LongTermMemory (Qdrant)                  │
│                                                       │
│  审查完成后自动保存：                                   │
│  {type: "review", contract_name, memory_text, ...}    │
│                                                       │
│  查询：语义检索历史审查记录                              │
│  API: GET /memory/recall, GET /memory/history         │
└─────────────────────────────────────────────────────┘
```

---

## 七、关键代码文件索引

| 文件 | 职责 |
|------|------|
| `src/agents/conversation_context.py` | 对话上下文管理（消息、轮次、Agent结果、共享数据） |
| `src/agents/multi_turn_handler.py` | 多轮对话处理（意图识别→Agent执行→结果存储→追问回答） |
| `src/agents/intent_recognizer.py` | 意图识别（LLM Function Calling） |
| `src/memory/long_term_memory.py` | 长期记忆（Qdrant 向量存储） |
| `src/memory/private_memory.py` | Agent私有记忆（已定义，未使用） |
| `src/memory/shared_memory.py` | 共享记忆管理器（已定义，未使用） |
| `src/memory/memory_layer.py` | 记忆层次枚举（CONTEXT/ANALYSIS/DECISION） |
| `src/api/task_manager.py` | 任务管理（调用handler + 保存长期记忆） |
| `src/api/routes.py` | API路由（/review/stream, /memory/recall 等） |
| `frontend/components/chat.py` | 前端聊天界面（session_state管理） |
