# 智能合同审查系统 - 技术架构文档

## 1. 系统总览

```mermaid
graph TB
    subgraph 外部层["🌐 外部层"]
        Client["前端客户端<br/>文件上传 + 多轮对话"]
        ExternalAPI["外部API调用方"]
    end

    subgraph 接入层["🚪 接入层"]
        FastAPI["FastAPI Server<br/>:8000"]
        Router["API Router<br/>/api/v1"]
    end

    subgraph 业务层["⚙️ 业务层"]
        TM["TaskManager<br/>任务管理器"]
        Coord["CoordinatorAgent<br/>智能协调器"]
        
        subgraph Agents["🤖 Agent集群"]
            DocParser["文档解析Agent"]
            ClauseAnalysis["条款分析Agent"]
            RiskAssess["风险评估Agent"]
            Compliance["合规检查Agent"]
            ReportGen["报告生成Agent"]
        end
    end

    subgraph 能力层["🔧 能力层"]
        subgraph Skills["📦 Skills技能库"]
            DocSkills["文档处理Skills<br/>PDF/DOCX/OCR"]
            LegalSkills["法律分析Skills<br/>条款/法规/案例"]
            RiskSkills["风险评估Skills<br/>识别/评分/缓解"]
            ReportSkills["报告生成Skills<br/>导出/可视化"]
        end
        
        subgraph Tools["🛠️ LangChain Tools"]
            ContractTools["合同审查工具"]
            LegalTools["法规查询工具"]
        end
    end

    subgraph 通信层["📡 通信层"]
        MCP["MCP Server<br/>JSON-RPC 2.0"]
        MsgBus["MessageBus<br/>消息总线"]
    end

    subgraph 记忆层["🧠 记忆层"]
        SharedMem["SharedMemoryManager<br/>共享记忆"]
        PrivMem["PrivateMemory<br/>私有记忆"]
        MemLayer["MemoryLayer<br/>CONTEXT/ANALYSIS/DECISION"]
    end

    subgraph 基础设施["🏗️ 基础设施"]
        LLM["LLM Factory<br/>MIMO/Anthropic/OpenAI"]
        Redis["Redis<br/>缓存/状态"]
        RabbitMQ["RabbitMQ<br/>消息队列"]
        ChromaDB["ChromaDB<br/>向量数据库"]
        FileStore["文件存储<br/>任务持久化"]
    end

    Client --> FastAPI
    ExternalAPI --> FastAPI
    FastAPI --> Router
    Router --> TM
    TM --> Coord
    Coord --> DocParser
    Coord --> ClauseAnalysis
    Coord --> RiskAssess
    Coord --> Compliance
    Coord --> ReportGen
    
    DocParser --> MCP
    ClauseAnalysis --> MCP
    RiskAssess --> MCP
    Compliance --> MCP
    ReportGen --> MCP
    
    MCP --> Skills
    Skills --> Tools
    
    Coord --> MsgBus
    MsgBus --> Agents
    
    Agents --> SharedMem
    Agents --> PrivMem
    SharedMem --> MemLayer
    
    Agents --> LLM
    TM --> RabbitMQ
    TM --> FileStore
    LLM --> Redis
    LegalSkills --> ChromaDB

    style 外部层 fill:#e3f2fd,stroke:#1565c0
    style 接入层 fill:#f3e5f5,stroke:#7b1fa2
    style 业务层 fill:#fff3e0,stroke:#ef6c00
    style 能力层 fill:#e8f5e9,stroke:#2e7d32
    style 通信层 fill:#fce4ec,stroke:#c62828
    style 记忆层 fill:#ede7f6,stroke:#4527a0
    style 基础设施 fill:#e0f7fa,stroke:#00695c
```

## 2. 文档导航

| 文档 | 说明 |
|------|------|
| [system-architecture.md](./system-architecture.md) | 系统架构详解 - 分层架构、技术栈、模块关系 |
| [agent-workflow.md](./agent-workflow.md) | Agent工作流 - 多Agent协作、消息通信、任务调度 |
| [data-model.md](./data-model.md) | 数据模型 - 记忆层次、共享记忆、数据流 |
| [infrastructure.md](./infrastructure.md) | 基础设施 - LLM、Redis、RabbitMQ、ChromaDB |

## 3. 核心设计原则

### 3.1 多Agent协作
- **职责分离**: 每个Agent专注一个领域（解析、条款、风险、合规、报告）
- **LLM驱动**: 所有Agent使用LLM进行智能分析，正则作为回退
- **动态调度**: CoordinatorAgent通过LLM智能决策任务执行顺序

### 3.2 分层记忆
- **CONTEXT层**: 合同上下文（原始文档、结构化条款、元数据）
- **ANALYSIS层**: 分析结果（条款分析、风险评估、合规检查）
- **DECISION层**: 决策历史（审查决策、冲突解决、最终建议）

### 3.3 可扩展性
- **Skills热插拔**: 通过SkillRegistry动态注册/注销技能
- **Agent可插拔**: 通过CoordinatorAgent动态注册Agent
- **MCP协议**: 标准化的工具通信协议

## 4. 技术栈速览

| 层级 | 技术 | 用途 |
|------|------|------|
| LLM | MIMO模型 (ChatAnthropic) | 智能分析和决策 |
| Agent框架 | LangChain + 自定义BaseAgent | Agent编排和协作 |
| API | FastAPI | RESTful接口 |
| 消息队列 | RabbitMQ | 异步任务处理 |
| 缓存 | Redis | 状态缓存 |
| 向量数据库 | ChromaDB | 法规知识检索 |
| 通信协议 | MCP (JSON-RPC 2.0) | 工具通信 |
