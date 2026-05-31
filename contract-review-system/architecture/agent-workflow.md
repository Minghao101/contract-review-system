# Agent 工作流与通信

## 1. 多Agent协作流程

```mermaid
graph TB
    Start(["用户提交合同"])
    
    Start --> TM["TaskManager<br/>接收任务"]
    TM --> Intent["意图识别<br/>LLM分析用户需求"]
    
    Intent --> Plan["CoordinatorAgent<br/>LLM生成执行计划"]
    
    Plan --> P1{"执行计划"}
    
    P1 -->|"阶段1"| S1["文档解析Agent<br/>提取合同信息"]
    S1 --> Mem1["写入CONTEXT层<br/>合同元数据 + 结构化条款"]
    
    Mem1 --> P2{"阶段2: 并行执行"}
    
    P2 -->|"分支1"| S2A["条款分析Agent<br/>分析条款完整性"]
    P2 -->|"分支2"| S2B["风险评估Agent<br/>识别和评估风险"]
    P2 -->|"分支3"| S2C["合规检查Agent<br/>检查法规合规性"]
    
    S2A --> Mem2["写入ANALYSIS层<br/>条款/风险/合规分析结果"]
    S2B --> Mem2
    S2C --> Mem2
    
    Mem2 --> P3{"阶段3"}
    P3 --> S3["报告生成Agent<br/>汇总生成审查报告"]
    
    S3 --> Mem3["写入DECISION层<br/>最终审查建议"]
    Mem3 --> Result["返回审查报告"]
    Result --> End(["用户获取结果"])

    style Start fill:#e3f2fd,stroke:#1565c0
    style End fill:#e3f2fd,stroke:#1565c0
    style Plan fill:#fff3e0,stroke:#ef6c00
    style S1 fill:#e8f5e9,stroke:#2e7d32
    style S2A fill:#e8f5e9,stroke:#2e7d32
    style S2B fill:#e8f5e9,stroke:#2e7d32
    style S2C fill:#e8f5e9,stroke:#2e7d32
    style S3 fill:#e8f5e9,stroke:#2e7d32
    style Mem1 fill:#ede7f6,stroke:#4527a0
    style Mem2 fill:#ede7f6,stroke:#4527a0
    style Mem3 fill:#ede7f6,stroke:#4527a0
```

## 2. CoordinatorAgent 智能调度

```mermaid
flowchart TB
    Input["接收任务<br/>contract_text + contract_type"]
    
    Input --> LLM1["LLM意图识别<br/>理解用户需求"]
    LLM1 --> GetAgents["获取已注册Agent列表"]
    GetAgents --> LLM2["LLM规划<br/>生成执行计划"]
    
    LLM2 --> Plan["执行计划<br/>JSON格式"]
    
    Plan --> Parse["解析计划"]
    
    Parse --> Check{"检查依赖"}
    
    Check -->|"无依赖"| Parallel["并行执行"]
    Check -->|"有依赖"| Sequential["串行执行"]
    
    Parallel --> Exec["执行Agent.process()"]
    Sequential --> Exec
    
    Exec --> Collect["收集结果"]
    Collect --> NextStep{"还有下一步?"}
    
    NextStep -->|"是"| Check
    NextStep -->|"否"| Final["汇总最终结果"]
    
    Final --> Output["返回审查结果"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style LLM1 fill:#fff3e0,stroke:#ef6c00
    style LLM2 fill:#fff3e0,stroke:#ef6c00
    style Plan fill:#f3e5f5,stroke:#7b1fa2
    style Parallel fill:#e8f5e9,stroke:#2e7d32
    style Sequential fill:#e8f5e9,stroke:#2e7d32
```

## 3. 消息总线通信

```mermaid
graph TB
    subgraph MessageBus["MessageBus 消息总线"]
        Subscribers["订阅者表<br/>{agent_id: [callback]}"]
        MsgQueue["消息队列"]
    end

    subgraph Senders["发送方"]
        Coord["CoordinatorAgent"]
        DocP["DocumentParserAgent"]
        Clause["ClauseAnalysisAgent"]
        Risk["RiskAssessmentAgent"]
        Comp["ComplianceCheckerAgent"]
        Report["ReportGeneratorAgent"]
    end

    subgraph MessageTypes["消息类型"]
        TA["TASK_ASSIGN<br/>任务分配"]
        TR["TASK_RESULT<br/>任务结果"]
        Q["QUERY<br/>查询请求"]
        R["RESPONSE<br/>查询响应"]
        N["NOTIFICATION<br/>通知"]
        E["ERROR<br/>错误"]
    end

    Coord -->|"publish()"| MsgQueue
    MsgQueue -->|"deliver()"| DocP
    MsgQueue -->|"deliver()"| Clause
    MsgQueue -->|"deliver()"| Risk
    MsgQueue -->|"deliver()"| Comp
    MsgQueue -->|"deliver()"| Report

    DocP -->|"subscribe()"| Subscribers
    Clause -->|"subscribe()"| Subscribers
    Risk -->|"subscribe()"| Subscribers
    Comp -->|"subscribe()"| Subscribers
    Report -->|"subscribe()"| Subscribers

    style MessageBus fill:#fce4ec,stroke:#c62828
    style Senders fill:#e3f2fd,stroke:#1565c0
```

## 4. AgentMessage 数据结构

```mermaid
classDiagram
    class AgentMessage {
        +str message_id
        +str sender_id
        +str receiver_id
        +MessageType message_type
        +Dict content
        +str correlation_id
        +datetime timestamp
        +to_dict() Dict
        +from_dict(data) AgentMessage
    }

    class MessageType {
        <<enumeration>>
        TASK_ASSIGN
        TASK_RESULT
        QUERY
        RESPONSE
        NOTIFICATION
        ERROR
    }

    class MessageBus {
        +Dict subscribers
        +List message_queue
        +subscribe(agent_id, callback)
        +unsubscribe(agent_id)
        +publish(message)
        +deliver()
    }

    AgentMessage --> MessageType
    MessageBus --> AgentMessage
```

## 5. 各Agent职责与输入输出

### 5.1 DocumentParserAgent（文档解析Agent）

```mermaid
graph LR
    Input["输入<br/>contract_text"] 
    Input --> Chunk["语义分块<br/>chunk_size=12000"]
    Chunk --> LLM["LLM提取<br/>单次调用"]
    LLM --> Output["输出<br/>• meta: 元信息<br/>• clauses: 结构化条款<br/>• key_terms: 关键术语"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style Output fill:#e8f5e9,stroke:#2e7d32
```

### 5.2 ClauseAnalysisAgent（条款分析Agent）

```mermaid
graph LR
    Input["输入<br/>contract_text<br/>review_focus?"]
    Input --> LLM["LLM条款分析"]
    LLM --> Output["输出<br/>• clause_completeness: 完整性<br/>• ambiguity_check: 歧义检测<br/>• fairness_assessment: 公平性<br/>• missing_clauses: 缺失条款"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style Output fill:#e8f5e9,stroke:#2e7d32
```

### 5.3 RiskAssessmentAgent（风险评估Agent）

```mermaid
graph LR
    Input["输入<br/>contract_text<br/>contract_type"]
    Input --> LLM["LLM风险评估"]
    LLM --> Output["输出<br/>• risk_level: 风险等级<br/>• identified_risks: 风险列表<br/>• risk_scores: 评分<br/>• mitigation_suggestions: 缓解建议"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style Output fill:#e8f5e9,stroke:#2e7d32
```

### 5.4 ComplianceCheckerAgent（合规检查Agent）

```mermaid
graph LR
    Input["输入<br/>contract_text<br/>contract_type"]
    Input --> LLM["LLM合规检查"]
    LLM --> Output["输出<br/>• compliance_status: 合规状态<br/>• required_clauses: 必备条款<br/>• missing_clauses: 缺失条款<br/>• regulatory_issues: 法规问题"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style Output fill:#e8f5e9,stroke:#2e7d32
```

### 5.5 ReportGeneratorAgent（报告生成Agent）

```mermaid
graph LR
    Input["输入<br/>previous_results<br/>（所有分析结果）"]
    Input --> LLM["LLM报告生成"]
    LLM --> Output["输出<br/>• executive_summary: 摘要<br/>• detailed_analysis: 详细分析<br/>• recommendations: 建议<br/>• risk_matrix: 风险矩阵"]

    style Input fill:#e3f2fd,stroke:#1565c0
    style Output fill:#e8f5e9,stroke:#2e7d32
```

## 6. 异步任务处理

```mermaid
stateDiagram-v2
    [*] --> Queued: 提交任务
    Queued --> Processing: 开始处理
    Processing --> Completed: 处理成功
    Processing --> Failed: 处理失败
    
    Queued: 状态: queued<br/>存储: RabbitMQ + 文件
    Processing: 状态: processing<br/>更新: 任务状态
    Completed: 状态: completed<br/>存储: 结果 + 文件
    Failed: 状态: failed<br/>存储: 错误信息

    Processing --> Processing: 中间状态更新
    
    Completed --> [*]
    Failed --> [*]
```

## 7. 错误处理与重试机制

```mermaid
flowchart TB
    Start["Agent.process()"]
    Start --> Try["尝试执行"]
    
    Try -->|"成功"| Success["返回结果"]
    
    Try -->|"LLM调用失败"| Retry{"重试次数<br/>< max_retries?"}
    Retry -->|"是"| Wait["等待退避"]
    Wait --> Try
    Retry -->|"否"| Error["返回错误"]
    
    Try -->|"JSON解析失败"| Repair["json_repair修复"]
    Repair -->|"修复成功"| Continue["继续处理"]
    Repair -->|"修复失败"| Fallback["正则回退"]
    Fallback -->|"回退成功"| Continue
    Fallback -->|"回退失败"| Error
    
    Continue --> Success

    style Start fill:#e3f2fd,stroke:#1565c0
    style Success fill:#e8f5e9,stroke:#2e7d32
    style Error fill:#fce4ec,stroke:#c62828
    style Retry fill:#fff3e0,stroke:#ef6c00
```
