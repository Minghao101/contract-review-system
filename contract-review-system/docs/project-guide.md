# 项目阅读指南 — 如何看懂合同审查系统

## 一、项目是做什么的

这是一个**多 Agent 协作的合同审查系统**。用户上传一份合同，系统自动：
1. 解析合同（提取条款、日期、金额）
2. 并行分析（风险评估 + 条款分析 + 合规检查）
3. 人工审批（可选）
4. 生成审查报告

技术栈：LangChain + LangGraph + FastAPI + Streamlit + Ollama/OpenAI

---

## 二、目录结构速查

```
contract-review-system/
├── src/
│   ├── agents/          # 核心：所有 Agent 实现（最重要）
│   ├── workflow/         # LangGraph 工作流定义
│   ├── memory/           # 共享记忆系统
│   ├── api/              # FastAPI 后端接口
│   ├── skills/           # 工具技能（PDF解析、OCR等）
│   ├── tools/            # LangChain Tools 封装
│   ├── mcp/              # MCP 协议实现
│   ├── services/         # 外部服务（向量存储等）
│   └── utils/            # 工具函数（LLM工厂、日志等）
├── frontend/             # Streamlit 前端
├── config/               # 配置文件
├── tests/                # 测试
└── docs/                 # 文档
```

---

## 三、核心阅读路线（按顺序）

### 第 1 步：理解 Agent 基类

**文件：** [src/agents/base_agent.py](src/agents/base_agent.py)

这是所有 Agent 的父类，理解它就理解了所有 Agent 的共同行为：

```
BaseAgent
├── agent_id, name, role          # 身份信息
├── llm                           # LLM 实例（由 llm_factory 创建）
├── chat(message)                 # 与 LLM 对话（返回字符串）
├── chat_structured(...)          # 与 LLM 对话（返回 Pydantic 模型）★
├── prompt_template               # 子类定义的 prompt 模板
├── output_model                  # 子类定义的输出 schema
├── read_shared() / write_shared()  # 读写共享记忆
├── publish_event()               # 发布事件
└── process(task)                 # 抽象方法：处理任务（子类必须实现）
```

**关键方法 `chat_structured()` 的流程：**
```
prompt_template.format_messages(**kwargs)
    → llm.with_structured_output(output_model).ainvoke(messages)
    → 返回 Pydantic 模型实例
    → 如果失败，fallback 到 raw chat + JSON 解析
```

### 第 2 步：理解 5 个专业 Agent

每个 Agent 都继承 BaseAgent，职责单一：

| Agent | 文件 | 职责 | 输出 Schema |
|-------|------|------|------------|
| CoordinatorAgent | [coordinator_agent.py](src/agents/coordinator_agent.py) | 协调多Agent协作、处理问候和未知意图 | Dict |
| DocumentParserAgent | [document_parser_agent.py](src/agents/document_parser_agent.py) | 解析合同，提取条款/日期/金额 | DocumentExtractionResult |
| ClauseAnalysisAgent | [clause_analysis_agent.py](src/agents/clause_analysis_agent.py) | 分析条款完整性、模糊性、权利义务 | ClauseAnalysisResult |
| RiskAssessmentAgent | [risk_assessment_agent.py](src/agents/risk_assessment_agent.py) | 评估合同风险，给出修改建议 | RiskAssessmentResult |
| ComplianceCheckerAgent | [compliance_checker_agent.py](src/agents/compliance_checker_agent.py) | 检查合同是否符合法律法规 | ComplianceCheckResult |
| ReportGeneratorAgent | [report_generator_agent.py](src/agents/report_generator_agent.py) | 汇总分析结果，生成审查报告 | ReportResult |

**每个 Agent 的共同模式：**
```python
class XxxAgent(BaseAgent):
    output_model = XxxResult                    # 1. 定义输出 schema
    prompt_template = ChatPromptTemplate(...)    # 2. 定义 prompt 模板

    async def process(self, task):              # 3. 实现 process()
        contract_text = self.read_shared(...)   #    从共享记忆读数据
        result = await self.chat_structured(...)#    调用 LLM
        self.write_shared(result, ...)          #    写入共享记忆
        self.publish_event(BusinessEvent.XXX)   #    发布事件
        return result
```

### 第 3 步：理解 Schema 定义

**文件：** [src/agents/schemas.py](src/agents/schemas.py)

所有 Agent 的输出都用 Pydantic 模型定义，替代了手动 JSON 解析：

```python
# 风险评估的输出结构
class RiskAssessmentResult(BaseModel):
    risk_level: str              # "low" / "medium" / "high" / "critical"
    risks: List[RiskItem]        # 风险列表
    recommendations: List[RiskRecommendation]  # 建议列表
    summary: RiskSummary         # 摘要
```

LLM 的输出会自动验证并转换为这些模型实例。

### 第 4 步：理解事件驱动协作

**文件：** [src/agents/business_events.py](src/agents/business_events.py)

Agent 之间通过事件协作，事件链路：

```
task.created (调度器发布)
  → DocumentParser 处理
    → document.parsed (发布)
      → RiskAssessor + ClauseAnalyst + ComplianceChecker 并行处理
        → risk.analyzed / clause.analyzed / compliance.checked (发布)
          → ReportGenerator 等待聚合所有事件后处理
            → task.completed (发布)
              → MultiTurnHandler 收到结果返回给用户
```

### 第 5 步：理解 LangGraph 工作流

**文件：** [src/workflow/review_workflow.py](src/workflow/review_workflow.py)

工作流用 LangGraph StateGraph 定义，是事件驱动的替代方案：

```
START → route_by_intent → parse_document → after_parse
    → parallel_analysis(子图) → human_review(interrupt) → generate_report → END
```

**三大高级特性：**
- **Checkpoint** (`MemorySaver`)：每个 session 的状态自动持久化
- **Human-in-the-loop** (`interrupt`)：报告生成前暂停等待用户审批
- **Subgraph**：并行分析（risk + clause + compliance）封装为子图

### 第 6 步：理解多轮对话处理器

**文件：** [src/agents/multi_turn_handler.py](src/agents/multi_turn_handler.py)

这是系统的**入口协调器**，负责：
1. 接收用户消息
2. 调用 IntentRecognizer 识别意图
3. 根据意图选择执行路径（LangGraph 工作流）
4. 返回结果给前端

```python
handler = MultiTurnHandler()
result = await handler.handle_message(
    session_id="xxx",
    user_message="请审查这份合同",
    contract_text="合同内容...",
)
```

**执行路径：**
- 主路径：`_execute_with_langgraph()` → LangGraph StateGraph
- 回退路径：如果 LangGraph 不可用，自动回退到事件驱动

---

## 四、数据流全景

```
用户上传合同 (Streamlit/FastAPI)
    │
    ▼
MultiTurnHandler.handle_message()
    │
    ├── IntentRecognizer → 识别意图 (contract_review)
    │
    ├── SharedMemoryManager → 写入 contract_text
    │
    ├── LangGraph 工作流（主路径）★
    │   └── ContractReviewWorkflow.run()
    │       → StateGraph 执行
    │       → Checkpoint 持久化
    │       → interrupt 等待审批
    │       → 返回最终结果
    │
    └── 回退路径
        └── 事件驱动（LangGraph 不可用时）
    │
    ▼
返回审查结果给前端
```

---

## 五、共享记忆系统

**文件：** [src/memory/](src/memory/)

```
SharedMemoryManager
├── CONTEXT 层    # 合同上下文（contract_text, contract_type）
├── ANALYSIS 层   # 分析结果（各 Agent 的输出）
└── DECISION 层   # 决策历史（最终报告、风险等级）
```

Agent 通过 `read_shared(key, layer)` / `write_shared(key, value, layer)` 读写数据。

---

## 六、关键文件索引

| 我想了解... | 看这个文件 |
|------------|-----------|
| Agent 基类和共同行为 | [base_agent.py](src/agents/base_agent.py) |
| 协调器Agent（多Agent协作） | [coordinator_agent.py](src/agents/coordinator_agent.py) |
| 所有输出 Schema | [schemas.py](src/agents/schemas.py) |
| 文档解析逻辑 | [document_parser_agent.py](src/agents/document_parser_agent.py) |
| 风险评估逻辑 | [risk_assessment_agent.py](src/agents/risk_assessment_agent.py) |
| 条款分析逻辑 | [clause_analysis_agent.py](src/agents/clause_analysis_agent.py) |
| 合规检查逻辑 | [compliance_checker_agent.py](src/agents/compliance_checker_agent.py) |
| 报告生成逻辑 | [report_generator_agent.py](src/agents/report_generator_agent.py) |
| 事件定义 | [business_events.py](src/agents/business_events.py) |
| 意图识别 | [intent_recognizer.py](src/agents/intent_recognizer.py) |
| LangGraph 工作流 | [review_workflow.py](src/workflow/review_workflow.py) |
| 多轮对话调度 | [multi_turn_handler.py](src/agents/multi_turn_handler.py) |
| LLM 创建 | [llm_factory.py](src/utils/llm_factory.py) |
| API 接口 | [routes.py](src/api/routes.py) |
| 前端界面 | [frontend/](frontend/) |
| 测试用例 | [tests/](tests/) |

---

## 七、快速上手

1. **看一个 Agent 的完整流程：** 从 `risk_assessment_agent.py` 的 `process()` 方法开始，追踪它如何调用 `chat_structured()`、写入共享记忆、发布事件。

2. **看工作流如何编排：** 从 `review_workflow.py` 的 `create_review_workflow()` 开始，理解图的节点、边、条件路由。

3. **看系统入口：** 从 `multi_turn_handler.py` 的 `handle_message()` 开始，理解用户请求如何路由到各 Agent。

4. **跑测试验证：** `python -m pytest tests/test_agents.py -v`，观察 4 个 Agent 的测试输出。
