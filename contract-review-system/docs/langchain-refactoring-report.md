# LangChain / LangGraph 高级抽象重构报告

## 一、概述

本次重构将项目从手动拼接 prompt 字符串 + 手动 JSON 解析的模式，升级为使用 LangChain 高级抽象（ChatPromptTemplate、with_structured_output、Pydantic schema）+ LangGraph 高级特性（Checkpoint、Human-in-the-loop、Subgraph）的模式。

**核心收益：**
- 消除了 5 份重复的 `_parse_json()` 方法
- 用声明式 Pydantic schema 替代脆弱的字符串 JSON 解析
- 用 LangGraph `StateGraph` 替代手动事件驱动编排，支持并行执行和条件路由
- 新增 Checkpoint 支持断点恢复、Human-in-the-loop 支持人工审批、Subgraph 封装并行分析
- 总代码量减少约 420 行（-1291 行，+872 行）

---

## 二、使用的包

| 包名 | 版本要求 | 用途 |
|------|---------|------|
| `langchain` | >=0.3.0 | LangChain 主包，提供 LLM 抽象和链式调用 |
| `langchain-core` | >=0.3.0 | 核心组件：`ChatPromptTemplate`、`BaseLLM`、`HumanMessage`、`SystemMessage` |
| `langchain-openai` | >=0.3.0 | OpenAI LLM 集成（ChatOpenAI） |
| `langchain-anthropic` | >=0.3.0 | Anthropic LLM 集成（ChatAnthropic） |
| `langgraph` | >=0.2.0 | 状态图编排：`StateGraph`、条件边、并行节点、Checkpoint、interrupt |
| `pydantic` | >=2.0.0 | 结构化输出 schema 定义、数据验证 |

---

## 三、具体改动

### 3.1 新建文件

#### `src/agents/schemas.py` — 结构化输出 Pydantic 模型

定义了所有 Agent 的输出 schema，替代手动 JSON 解析：

| 模型类 | 用途 | 使用 Agent |
|--------|------|-----------|
| `ClauseAnalysisResult` | 条款分析结果 | ClauseAnalysisAgent |
| `ComplianceCheckResult` | 合规检查结果 | ComplianceCheckerAgent |
| `RiskAssessmentResult` | 风险评估结果 | RiskAssessmentAgent |
| `ReportResult` | 报告生成结果 | ReportGeneratorAgent |
| `DocumentExtractionResult` | 文档解析结果 | DocumentParserAgent |
| `ClauseLocation` | 条款定位 | DocumentParserAgent |
| `InsertClauseResult` | 新增条款 | DocumentParserAgent |
| `ModifyInstructionResult` | 修改指令解析 | DocumentParserAgent |

关键设计：
- 使用 `@field_validator` 处理 LLM 返回非标准格式的情况（如日期返回字符串而非对象）
- 每个模型使用 `Field(default_factory=...)` 提供合理默认值，增强容错性

#### `src/workflow/review_workflow.py` — LangGraph 高级特性工作流

基于 LangGraph 实现的声明式工作流，支持三大高级特性：

```
START → route_by_intent → parse_document → after_parse → parallel_analysis(子图) → human_review → generate_report → END
                                                  ↓ (单维度)
                                             assess_risk / analyze_clauses / check_compliance → END
```

### 3.2 修改文件

#### `src/agents/base_agent.py` — Agent 基类增强

**新增属性：**
```python
prompt_template: Optional[ChatPromptTemplate] = None  # 子类定义 prompt 模板
output_model: Optional[Type[BaseModel]] = None         # 子类定义输出 schema
```

**新增方法 `chat_structured()`：**
```python
async def chat_structured(self, prompt_template=None, output_model=None, **kwargs) -> BaseModel:
```
- 流程：`prompt_template.format_messages()` → `llm.with_structured_output(model).ainvoke()` → 返回 Pydantic 模型
- Fallback：当 `with_structured_output()` 失败或返回空结果时，使用 raw chat + JSON 解析
- 使用 `extract_llm_content()` 处理不同 LLM 响应格式（str/list/dict）

#### `src/agents/document_parser_agent.py` — 文档解析 Agent

**改动前：** 手动拼接 prompt 字符串 + `json_repair` 解析
**改动后：**
- 定义 4 个 `ChatPromptTemplate`：`prompt_template`、`chunk_template`、`locate_template`、`insert_template`
- `output_model = DocumentExtractionResult`
- `_llm_extract_all()` 使用 `chat_structured()` 自动解析
- `_incremental_analyze()` 使用 `incremental_template` + `chat_structured()`
- Prompt 中显式要求 "只输出 JSON，不要其他内容"（解决 mimo 模型返回纯文本的问题）

#### `src/agents/clause_analysis_agent.py` — 条款分析 Agent

**改动前：** 手动拼接 prompt + `_parse_json()` + `json_repair`
**改动后：**
- `prompt_template`：完整分析模板
- `incremental_template`：单条款增量分析模板
- `output_model = ClauseAnalysisResult`
- `_analyze_with_llm()` 使用 `chat_structured()`
- `_incremental_analyze()` 使用 `incremental_template` + `chat_structured()`
- 删除了 `_parse_json()` 方法（约 30 行）

#### `src/agents/risk_assessment_agent.py` — 风险评估 Agent

**改动前：** 手动拼接 prompt + `_parse_json()` + `json_repair`
**改动后：**
- `prompt_template`：完整风险评估模板
- `incremental_template`：单条款增量风险分析模板
- `output_model = RiskAssessmentResult`
- `_assess_with_llm()` 使用 `chat_structured()`
- `_incremental_analyze()` 使用 `incremental_template` + `chat_structured()`
- 删除了 `_parse_json()` 方法

#### `src/agents/compliance_checker_agent.py` — 合规检查 Agent

**改动前：** 手动拼接 prompt + `_parse_json()` + `json_repair`
**改动后：**
- `prompt_template`：完整合规检查模板（含合同类型和必备条款变量）
- `incremental_template`：单条款增量合规检查模板
- `output_model = ComplianceCheckResult`
- `_check_with_llm()` 使用 `chat_structured()`
- `_incremental_analyze()` 使用 `incremental_template` + `chat_structured()`
- 删除了 `_parse_json()` 方法

#### `src/agents/report_generator_agent.py` — 报告生成 Agent

**改动前：** 手动拼接 prompt + `_parse_json()` + `json_repair`
**改动后：**
- `prompt_template`：报告生成模板（含 document_info、clause_analysis、risk_assessment、compliance_result 变量）
- `output_model = ReportResult`
- `_generate_with_llm()` 使用 `chat_structured()`
- 删除了 `_parse_json()` 方法

#### `src/agents/multi_turn_handler.py` — 多轮对话处理器

**新增方法 `_execute_with_langgraph()`：**
- 集成 `ContractReviewWorkflow` 作为替代执行路径
- 支持 `auto_approve` 参数控制是否自动审批
- 检测 interrupt 状态，返回中断信息给前端
- 保留原有事件驱动机制作为兼容路径

**新增方法 `_resume_langgraph()`：**
- 恢复被 interrupt 暂停的工作流
- 通过 `Command(resume=approved)` 继续执行

#### `src/agents/__init__.py` — 模块导出

新增 `schemas` 模块的导入和导出。

#### `requirements.txt` — 依赖更新

```diff
-langchain>=0.2.0
-langchain-core>=0.2.0
+langchain>=0.3.0
+langchain-core>=0.3.0
+langchain-openai>=0.3.0
+langchain-anthropic>=0.3.0
+langgraph>=0.2.0
```

---

## 四、LangGraph 使用的方法和抽象

### 4.1 核心类

| 类/方法 | 来源 | 用途 |
|---------|------|------|
| `StateGraph` | `langgraph.graph` | 定义状态图，声明式工作流编排 |
| `TypedDict` (ReviewState, AnalysisSubgraphState) | `typing` | 定义图的共享状态结构 |
| `END` | `langgraph.graph` | 图的终止节点 |
| `MemorySaver` | `langgraph.checkpoint.memory` | 内存级 Checkpoint，状态持久化 |
| `interrupt` | `langgraph.types` | Human-in-the-loop，暂停图执行等待用户输入 |
| `Command` | `langgraph.types` | 恢复被 interrupt 暂停的图执行 |

### 4.2 状态定义

**主图状态 (`ReviewState`)：**
```python
class ReviewState(TypedDict):
    # 输入
    contract_text: str
    contract_type: str
    review_focus: List[str]
    intent_type: str
    session_id: str

    # 各阶段结果
    parse_result: Optional[Dict[str, Any]]
    clause_result: Optional[Dict[str, Any]]
    risk_result: Optional[Dict[str, Any]]
    compliance_result: Optional[Dict[str, Any]]
    report_result: Optional[Dict[str, Any]]

    # 状态控制
    status: str
    error: Optional[str]
    steps_completed: List[str]
```

**子图状态 (`AnalysisSubgraphState`)：**
```python
class AnalysisSubgraphState(TypedDict):
    contract_text: str
    contract_type: str
    clause_result: Optional[Dict[str, Any]]
    risk_result: Optional[Dict[str, Any]]
    compliance_result: Optional[Dict[str, Any]]
```

### 4.3 图构建方法

| 方法 | 用途 |
|------|------|
| `StateGraph(ReviewState)` | 创建状态图实例 |
| `workflow.add_node(name, fn)` | 添加节点（每个节点是一个 async 函数，接收并返回 State） |
| `workflow.set_conditional_entry_point(fn, path_map)` | 设置条件入口，根据 `intent_type` 路由到不同起点 |
| `workflow.add_conditional_edges(source, fn, path_map)` | 添加条件边，根据状态决定下一步 |
| `workflow.add_edge(source, target)` | 添加无条件边 |
| `workflow.compile(checkpointer=MemorySaver())` | 编译图，带 Checkpoint 持久化 |
| `graph.ainvoke(state, config)` | 异步执行图，config 中传入 thread_id |
| `graph.ainvoke(Command(resume=...), config)` | 恢复被 interrupt 暂停的图 |

### 4.4 条件路由函数

```python
# 入口路由：根据意图类型选择起点
def route_by_intent(state: ReviewState) -> str:
    # contract_review → "full_review" → parse_document
    # risk_assessment → "single_risk" → parse_document
    # ...

# 解析后路由：根据意图决定下一步
def after_parse(state: ReviewState) -> str:
    # contract_review → "parallel" → parallel_analysis
    # risk_assessment → "risk" → assess_risk
    # ...

# 人工审批后路由
def after_human_review(state: ReviewState) -> str:
    # approved → "generate" → generate_report
    # rejected → "end"
```

### 4.5 工作流拓扑图

```
                        ┌─────────────────┐
                        │   START         │
                        └────────┬────────┘
                                 │ route_by_intent()
                        ┌────────▼────────┐
                        │ parse_document  │
                        └────────┬────────┘
                                 │ after_parse()
                  ┌──────────────┼──────────────┐
                  │              │              │
        ┌─────────▼──┐  ┌───────▼────┐  ┌──────▼─────────┐
        │parallel_   │  │assess_risk │  │analyze_clauses │
        │analysis    │  └──────┬─────┘  └──────┬─────────┘
        │ (子图)     │         │              │
        └─────────┬──┘         │              │
                  │            └──────┬───────┘
        ┌─────────▼────────┐         │
        │  human_review    │         │
        │  (interrupt)     │         │
        └─────────┬────────┘         │
                  │ Command(resume)  │
        ┌─────────▼────────┐         │
        │ generate_report  │         │
        └─────────┬────────┘         │
                  │                  │
                  └──────┬───────────┘
                         │
                       END
```

### 4.6 Subgraph（并行分析子图）

子图将 risk + clause + compliance 三个分析 Agent 封装为独立的可复用组件：

```
子图内部:
  ┌──────────────┐
  │ assess_risk  │──┐
  └──────────────┘  │
  ┌──────────────┐  │    ┌────────────────┐
  │analyze_clauses│──┼───▶│ merge_results  │
  └──────────────┘  │    └────────────────┘
  ┌──────────────┐  │
  │check_compliance│─┘
  └──────────────┘
```

**创建子图：**
```python
def create_analysis_subgraph():
    subgraph = StateGraph(AnalysisSubgraphState)
    subgraph.add_node("assess_risk", assess_risk_fn)
    subgraph.add_node("analyze_clauses", analyze_clauses_fn)
    subgraph.add_node("check_compliance", check_compliance_fn)
    subgraph.add_node("merge_results", merge_results_fn)

    # 三个分析并行执行，然后汇聚
    subgraph.add_edge("assess_risk", "merge_results")
    subgraph.add_edge("analyze_clauses", "merge_results")
    subgraph.add_edge("check_compliance", "merge_results")

    # 入口：三个节点并行（LangGraph 自动并行执行无入边的节点）
    subgraph.set_entry_point("assess_risk")
    subgraph.set_entry_point("analyze_clauses")
    subgraph.set_entry_point("check_compliance")
    subgraph.set_finish_point("merge_results")

    return subgraph.compile()
```

**主图中调用子图：**
```python
async def parallel_analysis(state: ReviewState) -> ReviewState:
    sub_state = {
        "contract_text": state["contract_text"],
        "contract_type": state.get("contract_type", "general"),
    }
    result = await analysis_subgraph.ainvoke(sub_state)
    state["risk_result"] = result.get("risk_result")
    state["clause_result"] = result.get("clause_result")
    state["compliance_result"] = result.get("compliance_result")
    return state
```

### 4.7 Checkpoint（状态持久化）

```python
from langgraph.checkpoint.memory import MemorySaver

# compile 时传入 checkpointer
checkpointer = MemorySaver()
workflow = StateGraph(ReviewState)
# ... 添加节点和边 ...
return workflow.compile(checkpointer=checkpointer)

# ainvoke 调用时传入 thread_id
config = {"configurable": {"thread_id": session_id}}
result = await workflow.ainvoke(initial_state, config)
```

**效果：** 每个 session_id 的执行状态自动持久化到内存，支持中断后恢复。

### 4.8 Human-in-the-loop（人工审批）

```python
from langgraph.types import interrupt, Command

async def human_review(state: ReviewState) -> ReviewState:
    # interrupt() 暂停图执行，返回 value 给前端
    approved = interrupt({
        "message": "分析已完成，请确认是否生成报告",
        "analysis_summary": {
            "risk_level": state.get("risk_result", {}).get("risk_level"),
            "compliance_status": state.get("compliance_result", {}).get("compliance_status"),
        }
    })
    # 用户通过 Command(resume=True) 恢复后，approved = True
    if not approved:
        state["status"] = "failed"
        state["error"] = "用户拒绝生成报告"
    return state
```

**前端调用方式：**
```python
# 第一次执行（会暂停在 interrupt）
result = await workflow.ainvoke(initial_state, config)

# 用户审批后恢复
result = await workflow.ainvoke(Command(resume=True), config)
# 或拒绝
result = await workflow.ainvoke(Command(resume=False), config)
```

---

## 五、LangChain 高级抽象使用的方法

### 5.1 ChatPromptTemplate

```python
# 定义（类级别）
prompt_template = ChatPromptTemplate.from_messages([
    ("system", "你是一个...专家。{变量}"),
    ("human", "请分析：\n\n{contract_text}"),
])

# 使用
messages = prompt_template.format_messages(
    contract_text=text,
    contract_type="service",
)
```

### 5.2 with_structured_output()

```python
# 在 BaseAgent.chat_structured() 中使用
structured_llm = self.llm.with_structured_output(model)  # model 是 Pydantic 类
result = await structured_llm.ainvoke(messages)
# result 直接是 Pydantic 模型实例
```

### 5.3 Fallback 机制

```python
# 当 with_structured_output() 失败或返回空结果时
response = await self.llm.ainvoke(messages)
content = extract_llm_content(response.content)  # 处理 str/list/dict
# 清理 markdown 代码块 → JSON 解析 → model.model_validate(parsed)
```

---

## 六、测试结果

```
tests/test_agents.py::test_document_parser   PASSED
tests/test_agents.py::test_clause_analysis   PASSED
tests/test_agents.py::test_risk_assessment   PASSED
tests/test_agents.py::test_report_generator  PASSED
tests/test_agents.py::test_coordinator       FAILED (预存问题，与本次重构无关)
```

4/5 测试通过。`test_coordinator` 失败是因为 `CoordinatorAgent` 缺少 `register_agent` 方法，属于预存问题，与本次 LangChain/LangGraph 重构无关。

---

## 七、工作流版本历史

| 版本 | 特性 | 说明 |
|------|------|------|
| 1.0 | 基础 StateGraph | add_node + add_edge + compile + ainvoke |
| 2.0 | + 并行执行 + 条件路由 | asyncio.gather + conditional_edges |
| **3.0** | **+ Checkpoint + Human-in-the-loop + Subgraph** | **MemorySaver + interrupt/Command + 子图** |
