# 智能合同审查系统 - LangChain多Agent方案

## 1. 系统概述

### 1.1 目标
构建一个通用智能合同审查系统，支持多种合同类型（劳动合同、采购合同、租赁合同、技术合同等），通过多Agent协作实现自动化的合同条款分析、风险识别、合规检查和修改建议。

### 1.2 核心技术栈
- **LLM**: MIMO模型 (自定义模型)
- **Agent框架**: LangChain + LangGraph
- **记忆系统**: LangChain Memory模块 + 自定义共享记忆
- **工具系统**: LangChain Tools + 自定义工具
- **工作流**: LangGraph (多Agent编排)

### 1.3 LangChain vs Claude Agent SDK 选择理由

| 特性 | LangChain | Claude Agent SDK |
|------|-----------|------------------|
| **模型支持** | 多种LLM (OpenAI, MIMO, 本地模型等) | 仅Claude |
| **Memory模块** | 内置多种Memory类型 | 需自定义 |
| **Tool系统** | 内置Tool抽象 | MCP协议 |
| **Agent编排** | LangGraph支持复杂工作流 | 有限 |
| **社区生态** | 丰富，插件多 | 官方支持 |
| **灵活性** | 高，可扩展 | 中等 |

**结论**: 使用MIMO模型时，LangChain是更好的选择

---

## 2. 系统架构（实际实现）

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          前端UI (对话界面)                               │
│                    文件上传 + 多轮对话 + 结果展示                         │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │ HTTP API
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI 后端 (main.py)                           │
│                    /api/v1/review  /api/v1/upload                       │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     TaskManager (任务管理器)                             │
│              意图识别 → Agent路由 → 执行 → 结果汇总                      │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CoordinatorAgent (协调器)                             │
│              LLM智能规划 → 动态执行计划 → 并行/串行调度                   │
└─────────────┬───────────────────────────────────────────────────────────┘
              │
              │  任务分配 & 结果汇总
              │
    ┌─────────┴─────────┬─────────────────────┬─────────────────────┐
    ▼                   ▼                     ▼                     ▼
┌─────────────┐   ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  文档解析    │   │  条款分析    │       │  风险评估    │       │  合规检查    │
│  Agent      │   │  Agent      │       │  Agent      │       │  Agent      │
│ (LLM驱动)  │   │ (LLM驱动)   │       │ (LLM驱动)   │       │ (LLM驱动)   │
└─────────────┘   └─────────────┘       └─────────────┘       └─────────────┘
        │               │                     │                     │
        │               │                     │                     │
        └───────────────┴──────────┬──────────┴─────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │      报告生成Agent           │
                    │      (汇总所有结果)          │
                    └─────────────────────────────┘
```

### 2.2 技术栈（实际使用）

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | MIMO模型 (ChatAnthropic/OpenAI) | 通过langchain封装 |
| Agent框架 | BaseAgent (自定义) | 继承ABC，统一process()接口 |
| Agent编排 | CoordinatorAgent (LLM动态规划) | 根据任务自动生成执行计划 |
| 记忆系统 | SharedMemoryManager + AgentPrivateMemory | 分层存储 + 上下文压缩 |
| 工具系统 | LangChain Tools + Skills | 4个LLM工具 + 3个文档处理Skills |
| API | FastAPI | RESTful接口 + 文件上传 |
| 消息队列 | RabbitMQ (可选) | 异步任务处理 |

### 2.3 目录结构

```
contract-review-system/
├── src/
│   ├── agents/                    # Agent模块
│   │   ├── base_agent.py          # Agent基类 (ABC)
│   │   ├── coordinator_agent.py   # 协调器 (LLM动态规划)
│   │   ├── document_parser_agent.py  # 文档解析Agent
│   │   ├── clause_analysis_agent.py  # 条款分析Agent
│   │   ├── risk_assessment_agent.py  # 风险评估Agent
│   │   ├── compliance_checker_agent.py  # 合规检查Agent
│   │   ├── report_generator_agent.py    # 报告生成Agent
│   │   ├── communication.py       # Agent间通信
│   │   ├── langchain_agent.py     # LangChain包装器
│   │   └── agent_tools.py         # 工具集成
│   ├── memory/                    # 记忆系统
│   │   ├── shared_memory.py       # 共享记忆管理器
│   │   ├── private_memory.py      # Agent私有记忆
│   │   └── memory_layer.py        # 记忆层次定义
│   ├── mcp/                       # MCP Server
│   │   ├── server.py              # MCP服务端
│   │   ├── client.py              # MCP客户端
│   │   └── protocol.py            # MCP协议定义
│   ├── skills/                    # Skills模块
│   │   ├── base_skill.py          # Skill基类
│   │   ├── skill_registry.py      # Skills注册器
│   │   └── document/              # 文档处理Skills
│   │       ├── pdf_reader.py
│   │       ├── docx_parser.py
│   │       └── ocr_processor.py
│   ├── tools/                     # LangChain工具
│   │   └── langchain_tools.py     # 4个合同审查工具
│   ├── api/                       # API模块
│   │   ├── main.py                # FastAPI入口
│   │   ├── routes.py              # API路由
│   │   └── task_manager.py        # 任务管理器
│   └── utils/                     # 工具函数
│       ├── llm_factory.py         # LLM工厂
│       ├── logger.py              # 日志
│       └── validators.py          # 验证器
├── config/                        # 配置
│   └── settings.py
├── daily_plan.md                  # 开发计划
└── plan_langchain.md              # 本文档
```

---

## 3. Agent角色定义（实际实现）

### 3.1 BaseAgent 基类
```python
# src/agents/base_agent.py
class BaseAgent(ABC):
    def __init__(self, agent_id, name, role, llm=None, description=""):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.llm = llm or get_llm()
        self.private_memory: Dict[str, Any] = {}

    @abstractmethod
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务（抽象方法）"""
        pass
```

### 3.2 协调器Agent (CoordinatorAgent)
**职责**: 智能任务调度、LLM动态规划、结果汇总

```python
# src/agents/coordinator_agent.py
class CoordinatorAgent(BaseAgent):
    async def process(self, task):
        # 1. LLM智能规划执行计划
        execution_plan = await self._plan_execution(task)
        # 2. 并行/串行混合执行
        results = await self._execute_plan(execution_plan, task, contract_text)
        # 3. 汇总所有结果
        final_result = self._aggregate_results(results, task)
        return final_result
```

默认执行计划（5个步骤）：
```
parse_document → [analyze_clauses, assess_risks, compliance_check] → generate_report
                   (并行执行3个Agent)                    (串行汇总)
```

### 3.3 文档解析Agent (DocumentParserAgent)
**职责**: 合同文档预处理、结构化信息提取

- LLM单次调用提取所有信息（基本信息、条款、日期、金额、术语）
- 长文本Map-Reduce分块处理
- JSON容错解析 + 正则回退

### 3.4 条款分析Agent (ClauseAnalysisAgent)
**职责**: 条款完整性、歧义检测、权利义务平衡分析

- 完整性评分（必备条款检查）
- 歧义表述识别
- 权利/义务数量统计与平衡性判断

### 3.5 风险评估Agent (RiskAssessmentAgent)
**职责**: 风险识别、量化、缓解建议

- LLM风险识别（责任、付款、IP、终止、争议等类别）
- `quantify_risk()`: 加权风险评分（severity × category权重）
- `suggest_mitigation()`: 按优先级生成缓解计划

### 3.6 合规检查Agent (ComplianceCheckerAgent)
**职责**: 法规合规检查、必备条款验证

- 7类合同必备条款库
- LLM合规分析 + 规则回退
- 自动计算合规分数

### 3.7 报告生成Agent (ReportGeneratorAgent)
**职责**: 汇总所有分析结果，生成专业审查报告

- 执行摘要 + 风险分类 + 建议列表
- 结论（建议签署/修改后签署/不建议签署）

**实现方式**: LangChain Agent + Tools

```python
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate
from langchain.tools import Tool

class DocumentParserAgent:
    def __init__(self, llm):
        self.llm = llm
        self.tools = self._create_tools()
        self.agent = self._create_agent()
    
    def _create_tools(self):
        """创建文档解析工具"""
        tools = [
            Tool(
                name="read_pdf",
                func=self.read_pdf,
                description="读取PDF文件并提取文本内容"
            ),
            Tool(
                name="extract_metadata",
                func=self.extract_metadata,
                description="从合同文本中提取元数据（标题、日期、当事人等）"
            ),
            Tool(
                name="identify_clauses",
                func=self.identify_clauses,
                description="识别合同中的条款和章节结构"
            ),
        ]
        return tools
    
    def _create_agent(self):
        """创建Agent"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的合同文档解析专家。
            你的任务是：
            1. 读取合同文档
            2. 提取关键元数据
            3. 识别合同结构和条款
            
            请使用提供的工具完成任务。"""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])
        
        agent = create_openai_tools_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    async def parse(self, document: str) -> dict:
        """解析合同文档"""
        result = await self.agent.ainvoke({
            "input": f"请解析以下合同文档并提取结构化信息：\n\n{document}"
        })
        return result
```

**输出到共享记忆**:
```json
{
  "document_id": "contract_001",
  "metadata": {
    "title": "技术服务合同",
    "parties": ["甲方: XX公司", "乙方: YY科技"],
    "date": "2024-01-15",
    "amount": "500000元",
    "type": "技术服务合同"
  },
  "structure": [
    {"clause_id": "1.0", "title": "合同标的", "content": "..."},
    {"clause_id": "2.0", "title": "价款及支付", "content": "..."}
  ]
}
```

### 3.3 条款分析Agent (Clause Analysis Agent)
**职责**: 逐条分析合同条款的合理性

**实现方式**: LangChain Agent + Memory

```python
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain

class ClauseAnalysisAgent:
    def __init__(self, llm):
        self.llm = llm
        self.memory = ConversationBufferMemory()
        self.tools = self._create_tools()
    
    def _create_tools(self):
        """创建条款分析工具"""
        tools = [
            Tool(
                name="analyze_clause",
                func=self.analyze_single_clause,
                description="分析单个条款的法律含义和合理性"
            ),
            Tool(
                name="detect_ambiguity",
                func=self.detect_ambiguity,
                description="检测条款中的歧义和模糊表述"
            ),
            Tool(
                name="check_completeness",
                func=self.check_completeness,
                description="检查条款的完整性和必要元素"
            ),
            Tool(
                name="analyze_relationships",
                func=self.analyze_relationships,
                description="分析条款之间的逻辑关系和一致性"
            ),
        ]
        return tools
    
    async def analyze(self, clauses: List[Dict]) -> Dict:
        """分析所有条款"""
        results = []
        for clause in clauses:
            # 使用Memory存储分析历史
            self.memory.save_context(
                {"input": f"分析条款: {clause['title']}"},
                {"output": f"开始分析条款: {clause['title']}"}
            )
            
            # 分析单个条款
            analysis = await self.analyze_single_clause(clause)
            results.append({
                "clause_id": clause["clause_id"],
                "analysis": analysis
            })
        
        return {"clauses": results}
    
    async def analyze_single_clause(self, clause: Dict) -> Dict:
        """分析单个条款"""
        prompt = f"""
        请分析以下合同条款：
        
        条款标题: {clause['title']}
        条款内容: {clause['content']}
        
        请从以下维度分析：
        1. 法律含义
        2. 合理性
        3. 完整性
        4. 潜在风险
        5. 改进建议
        """
        
        response = await self.llm.ainvoke(prompt)
        return {"analysis": response}
```

### 3.4 风险评估Agent (Risk Assessment Agent)
**职责**: 识别和评估合同风险

**实现方式**: LangChain Agent + Custom Tools

```python
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

class RiskInput(BaseModel):
    clause_text: str = Field(description="条款文本")
    context: dict = Field(description="合同上下文")

class RiskAssessmentAgent:
    def __init__(self, llm):
        self.llm = llm
        self.tools = self._create_tools()
        self.risk_rules = self._load_risk_rules()
    
    def _create_tools(self):
        """创建风险评估工具"""
        tools = [
            BaseTool(
                name="identify_risks",
                func=self.identify_risks,
                description="识别条款中的风险点",
                args_schema=RiskInput
            ),
            Tool(
                name="quantify_risk",
                func=self.quantify_risk,
                description="量化风险等级（高/中/低）"
            ),
            Tool(
                name="suggest_mitigation",
                func=self.suggest_mitigation,
                description="提供风险缓解建议"
            ),
            Tool(
                name="search_similar_cases",
                func=self.search_similar_cases,
                description="搜索类似风险案例"
            ),
        ]
        return tools
    
    def _load_risk_rules(self):
        """加载风险规则库"""
        return {
            "legal_risks": [
                "违约责任不明确",
                "争议解决机制缺失",
                "知识产权归属不清",
                "竞业限制条款过宽",
            ],
            "commercial_risks": [
                "付款条件模糊",
                "交付时间不明确",
                "验收标准缺失",
                "价格调整机制缺失",
            ],
            "operational_risks": [
                "执行难度过高",
                "资源要求不合理",
                "时间节点紧张",
            ]
        }
    
    async def assess(self, clauses: List[Dict], metadata: Dict) -> Dict:
        """评估合同风险"""
        risks = []
        for clause in clauses:
            clause_risks = await self.identify_risks(
                clause_text=clause["content"],
                context=metadata
            )
            risks.extend(clause_risks)
        
        # 量化风险
        risk_scores = []
        for risk in risks:
            score = await self.quantify_risk(risk)
            risk_scores.append({
                "risk": risk,
                "score": score
            })
        
        # 生成缓解建议
        mitigations = []
        for risk_score in risk_scores:
            mitigation = await self.suggest_mitigation(risk_score["risk"])
            mitigations.append({
                "risk": risk_score["risk"],
                "mitigation": mitigation
            })
        
        return {
            "risks": risks,
            "risk_scores": risk_scores,
            "mitigations": mitigations
        }
```

### 3.5 合规检查Agent (Compliance Checker Agent)
**职责**: 检查合同是否符合法律法规和行业规范

**实现方式**: LangChain Agent + Knowledge Base

```python
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings

class ComplianceCheckerAgent:
    def __init__(self, llm):
        self.llm = llm
        self.embeddings = OpenAIEmbeddings()
        self.knowledge_base = self._init_knowledge_base()
        self.tools = self._create_tools()
    
    def _init_knowledge_base(self):
        """初始化法律法规知识库"""
        # 加载法律法规文档到向量数据库
        return Chroma(
            collection_name="regulations",
            embedding_function=self.embeddings
        )
    
    def _create_tools(self):
        """创建合规检查工具"""
        tools = [
            Tool(
                name="search_regulations",
                func=self.search_regulations,
                description="检索相关法律法规"
            ),
            Tool(
                name="check_compliance",
                func=self.check_compliance,
                description="检查条款是否符合法规"
            ),
            Tool(
                name="verify_mandatory_clauses",
                func=self.verify_mandatory_clauses,
                description="验证必备条款是否存在"
            ),
            Tool(
                name="generate_compliance_report",
                func=self.generate_compliance_report,
                description="生成合规检查报告"
            ),
        ]
        return tools
    
    async def check(self, clauses: List[Dict], contract_type: str) -> Dict:
        """执行合规检查"""
        # 1. 获取该类型合同的必备条款
        mandatory_clauses = self.get_mandatory_clauses(contract_type)
        
        # 2. 检查必备条款是否缺失
        missing_clauses = await self.verify_mandatory_clauses(
            clauses, mandatory_clauses
        )
        
        # 3. 检查每个条款的合规性
        compliance_results = []
        for clause in clauses:
            result = await self.check_compliance(clause)
            compliance_results.append(result)
        
        # 4. 生成合规报告
        report = await self.generate_compliance_report(
            compliance_results, missing_clauses
        )
        
        return report
    
    async def search_regulations(self, query: str) -> List[str]:
        """检索相关法律法规"""
        results = self.knowledge_base.similarity_search(query, k=5)
        return [doc.page_content for doc in results]
    
    def get_mandatory_clauses(self, contract_type: str) -> List[str]:
        """获取合同类型的必备条款"""
        mandatory = {
            "劳动合同": ["工作内容", "工作地点", "工作时间", "劳动报酬", "社会保险"],
            "采购合同": ["标的物", "数量", "质量", "价款", "履行期限", "违约责任"],
            "租赁合同": ["租赁物", "租金", "租赁期限", "维修责任", "违约责任"],
            "技术合同": ["项目名称", "技术内容", "技术要求", "验收标准", "知识产权"],
        }
        return mandatory.get(contract_type, [])
```

---

## 4. 共享记忆系统设计

### 4.1 LangChain Memory集成

```python
from langchain.memory import (
    ConversationBufferMemory,
    ConversationSummaryMemory,
    VectorStoreRetrieverMemory
)
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
import redis
import json

class SharedMemoryManager:
    """Agent共享记忆管理器"""
    
    def __init__(self, contract_id: str):
        self.contract_id = contract_id
        
        # 使用Redis作为共享存储
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        
        # 使用向量数据库存储语义记忆
        self.embeddings = OpenAIEmbeddings()
        self.vector_store = Chroma(
            collection_name=f"contract_{contract_id}",
            embedding_function=self.embeddings
        )
        
        # 每个Agent的私有记忆
        self.agent_memories = {}
    
    def get_agent_memory(self, agent_id: str, memory_type: str = "buffer"):
        """获取Agent的私有记忆"""
        if agent_id not in self.agent_memories:
            if memory_type == "buffer":
                self.agent_memories[agent_id] = ConversationBufferMemory()
            elif memory_type == "summary":
                self.agent_memories[agent_id] = ConversationSummaryMemory(
                    llm=self.llm
                )
            elif memory_type == "vector":
                self.agent_memories[agent_id] = VectorStoreRetrieverMemory(
                    vectorstore=self.vector_store
                )
        
        return self.agent_memories[agent_id]
    
    def write_shared(self, agent_id: str, key: str, value: Any, layer: str):
        """写入共享记忆"""
        data = {
            "agent_id": agent_id,
            "key": key,
            "value": value,
            "layer": layer,
            "timestamp": datetime.now().isoformat()
        }
        
        # 存储到Redis
        redis_key = f"contract:{self.contract_id}:{layer}:{key}"
        self.redis_client.set(redis_key, json.dumps(data))
        
        # 同时存储到向量数据库（用于语义搜索）
        self.vector_store.add_texts(
            texts=[json.dumps(value)],
            metadatas=[{"agent_id": agent_id, "key": key, "layer": layer}]
        )
        
        # 通知其他Agent
        self._notify_agents(agent_id, key)
    
    def read_shared(self, agent_id: str, key: str, layer: str) -> Any:
        """读取共享记忆"""
        redis_key = f"contract:{self.contract_id}:{layer}:{key}"
        data = self.redis_client.get(redis_key)
        if data:
            return json.loads(data)["value"]
        return None
    
    def search_shared(self, query: str, layer: str = None) -> List[Any]:
        """语义搜索共享记忆"""
        search_kwargs = {"k": 5}
        if layer:
            search_kwargs["filter"] = {"layer": layer}
        
        results = self.vector_store.similarity_search(query, **search_kwargs)
        return [json.loads(doc.page_content) for doc in results]
    
    def _notify_agents(self, writer_agent: str, key: str):
        """通知其他Agent有新数据写入"""
        # 使用Redis Pub/Sub实现通知
        channel = f"contract:{self.contract_id}:updates"
        message = json.dumps({
            "writer_agent": writer_agent,
            "key": key,
            "timestamp": datetime.now().isoformat()
        })
        self.redis_client.publish(channel, message)
```

### 4.2 记忆层次结构

```python
class MemoryLayer:
    """记忆层次"""
    CONTEXT = "context"      # 合同上下文
    ANALYSIS = "analysis"    # 分析结果
    DECISION = "decision"    # 决策历史

# 使用示例
shared_memory = SharedMemoryManager("contract_001")

# 合同解析Agent写入上下文
shared_memory.write_shared(
    agent_id="parser",
    key="document_structure",
    value={"clauses": [...], "metadata": {...}},
    layer=MemoryLayer.CONTEXT
)

# 条款分析Agent读取上下文
structure = shared_memory.read_shared(
    agent_id="clause_analyzer",
    key="document_structure",
    layer=MemoryLayer.CONTEXT
)

# 条款分析Agent写入分析结果
shared_memory.write_shared(
    agent_id="clause_analyzer",
    key="analysis_results",
    value={"clause_1": {...}, "clause_2": {...}},
    layer=MemoryLayer.ANALYSIS
)
```

---

## 5. LangChain Tools设计

### 5.1 工具分类

```
tools/
├── document_tools/
│   ├── pdf_reader.py
│   ├── ocr_processor.py
│   ├── docx_parser.py
│   └── metadata_extractor.py
├── legal_tools/
│   ├── regulation_searcher.py
│   ├── case_retriever.py
│   ├── legal_ontology.py
│   └── template_matcher.py
├── risk_tools/
│   ├── risk_identifier.py
│   ├── risk_scorer.py
│   ├── mitigation_suggester.py
│   └── case_reference.py
└── common_tools/
    ├── text_processor.py
    ├── validator.py
    └── reporter.py
```

### 5.2 工具定义示例

```python
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

class PDFReaderInput(BaseModel):
    file_path: str = Field(description="PDF文件路径")

class PDFReaderTool(BaseTool):
    name = "pdf_reader"
    description = "读取PDF文件并提取文本内容"
    args_schema = PDFReaderInput
    
    def _run(self, file_path: str) -> str:
        """同步读取PDF"""
        import PyPDF2
        
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
        
        return text
    
    async def _arun(self, file_path: str) -> str:
        """异步读取PDF"""
        return self._run(file_path)

class RegulationSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")
    contract_type: Optional[str] = Field(description="合同类型", default=None)

class RegulationSearcherTool(BaseTool):
    name = "regulation_searcher"
    description = "检索相关法律法规"
    args_schema = RegulationSearchInput
    
    def _run(self, query: str, contract_type: str = None) -> list:
        """搜索法规"""
        # 连接到法规知识库
        # 返回相关法规列表
        pass
    
    async def _arun(self, query: str, contract_type: str = None) -> list:
        """异步搜索法规"""
        return self._run(query, contract_type)
```

### 5.3 工具注册

```python
from langchain.agents import initialize_agent, AgentType

def create_agent_with_tools(llm, tools, agent_type="openai-tools"):
    """创建带工具的Agent"""
    
    # 选择Agent类型
    if agent_type == "openai-tools":
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.OPENAI_TOOLS,
            verbose=True
        )
    elif agent_type == "react":
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.REACT_DOCSTORE,
            verbose=True
        )
    
    return agent

# 注册所有工具
all_tools = [
    PDFReaderTool(),
    OCRProcessorTool(),
    RegulationSearcherTool(),
    RiskIdentifierTool(),
    # ... 更多工具
]

# 创建Agent
agent = create_agent_with_tools(llm, all_tools)
```

---

## 6. 工作流程实现（实际）

### 6.1 完整审查流程

```python
# src/api/task_manager.py
class TaskManager:
    def __init__(self):
        self._coordinator = CoordinatorAgent()
        # 注册所有Agent
        self._coordinator.register_agent(DocumentParserAgent())
        self._coordinator.register_agent(ClauseAnalysisAgent())
        self._coordinator.register_agent(RiskAssessmentAgent())
        self._coordinator.register_agent(ComplianceCheckerAgent())
        self._coordinator.register_agent(ReportGeneratorAgent())

    async def process_sync(self, contract_text, contract_type, review_focus):
        return await self._coordinator.process({
            "contract_text": contract_text,
            "contract_type": contract_type,
            "review_focus": review_focus,
        })
```

### 6.2 CoordinatorAgent 智能调度

```python
# src/agents/coordinator_agent.py
class CoordinatorAgent(BaseAgent):
    async def _plan_execution(self, task):
        """LLM动态规划执行计划"""
        # 根据任务需求，LLM决定调用哪些Agent
        # 输出：[{task_name, agent_role, depends_on, parallel}]
        pass

    async def _execute_plan(self, plan, task, contract_text):
        """支持并行的DAG执行"""
        import asyncio
        results = {}
        completed = set()
        while len(completed) < len(plan):
            # 找出可执行的任务（依赖已满足）
            ready = [t for t in plan if t["depends_on"] ⊆ completed]
            # 并行执行
            task_results = await asyncio.gather(*[
                self._execute_single(name, agent, input)
                for name, agent, input in ready
            ])
            # 更新completed
        return results
```

### 6.3 默认执行计划

```
Step 1: parse_document (串行，必须先解析)
    ↓
Step 2: [analyze_clauses, assess_risks, compliance_check] (并行)
    ↓
Step 3: generate_report (串行，汇总所有结果)
```

---

## 7. 实现计划 (25天)

> **当前进度**: Day 1-14 ✅ 已完成 | Day 15-25 待开发
> **最后更新**: 2026-05-28

### 第一周: 基础架构搭建 ✅

**Day 1 (周一): 项目初始化** ✅
- [x] 创建项目目录结构
- [x] 初始化Python虚拟环境
- [x] 安装LangChain及相关依赖
- [x] 配置开发工具
- [x] 创建README文档

**Day 2 (周二): LangChain基础配置** ✅
- [x] 配置MIMO模型连接
- [x] 测试LLM调用
- [x] 实现基础Agent框架 (BaseAgent)
- [x] 编写配置管理代码 (Settings)

**Day 3 (周三): 共享记忆系统实现** ✅
- [x] 实现SharedMemoryManager类
- [x] 集成Redis存储
- [x] 集成向量数据库
- [x] 实现记忆通知机制

**Day 4 (周四): Agent私有记忆实现** ✅
- [x] 实现AgentPrivateMemory
- [x] 实现上下文压缩机制
- [x] 实现记忆层次定义 (MemoryLayer)

**Day 5 (周五): MCP Server基础架构** ✅
- [x] 实现MCP Server (MCPServer)
- [x] 实现MCP Client (MCPClient)
- [x] 实现MCP协议定义 (Protocol)
- [x] 实现Agent间通信 (MessageBus)

### 第二周: 核心Agent实现 ✅

**Day 6 (周一): 协调器Agent实现** ✅
- [x] 实现CoordinatorAgent (LLM动态规划)
- [x] 实现任务分配逻辑
- [x] 实现并行/串行混合执行
- [x] 实现结果汇总逻辑

**Day 7 (周二): 合同解析Agent实现** ✅
- [x] 实现DocumentParserAgent (LLM驱动)
- [x] 实现Map-Reduce长文本处理
- [x] 实现JSON容错解析
- [x] 实现数据标准化

**Day 8 (周三): 条款分析Agent实现** ✅
- [x] 实现ClauseAnalysisAgent (LLM驱动)
- [x] 实现完整性评分
- [x] 实现歧义检测
- [x] 实现正则回退

**Day 9 (周四): 风险评估Agent实现** ✅
- [x] 实现RiskAssessmentAgent (LLM驱动)
- [x] 实现风险量化 (quantify_risk)
- [x] 实现缓解建议 (suggest_mitigation)
- [x] 实现正则回退

**Day 10 (周五): 合规检查Agent实现** ✅
- [x] 实现ComplianceCheckerAgent (LLM驱动)
- [x] 实现7类合同必备条款库
- [x] 实现规则回退检查
- [x] 实现合规分数自动计算

### 第三周: Skills和集成 ✅

**Day 11 (周一): 文档处理Skills** ✅
- [x] 实现PDFReaderSkill
- [x] 实现DocxParserSkill
- [x] 实现OCRProcessorSkill
- [x] 测试文档处理Skills

**Day 12 (周二): 法律分析Skills** ✅
- [x] 实现ClauseParserSkill
- [x] 实现RegulationCheckerSkill
- [x] 实现CaseRetrieverSkill
- [x] 测试法律分析Skills

**Day 13 (周三): 风险管理Skills** ✅
- [x] 实现RiskIdentifierSkill
- [x] 实现RiskScorerSkill
- [x] 实现MitigationSuggesterSkill
- [x] 测试风险管理Skills

**Day 14 (周四): 报告生成Skills** ✅
- [x] 实现ReportGeneratorSkill
- [x] 实现VisualizationSkill
- [x] 实现ExportSkill
- [x] 测试报告生成Skills

**额外完成: API层和任务管理** ✅
- [x] 实现FastAPI应用入口 (main.py)
- [x] 实现API路由 (routes.py): /review, /upload, /tasks
- [x] 实现TaskManager (RabbitMQ + 文件持久化)
- [x] 实现DocumentParser (文件上传解析)
- [x] 实现SkillRegistry和AgentTools集成

### 第四周: 工具集成测试 🔄

**Day 15 (周五): 工具集成测试**
- [ ] 测试所有工具集成
- [ ] 修复发现的问题
- [ ] 优化工具性能
- [ ] 编写工具使用文档

**Day 16 (周一): Agent协作测试**
- [ ] 设计端到端测试用例
- [ ] 测试Agent间通信
- [ ] 测试共享记忆读写
- [ ] 测试并行处理

**Day 17 (周二): 记忆系统测试**
- [ ] 测试共享记忆并发性能
- [ ] 测试记忆通知机制
- [ ] 测试上下文压缩
- [ ] 优化记忆存储

**Day 18 (周三): 工作流测试**
- [ ] 测试LangGraph工作流
- [ ] 测试条件路由
- [ ] 测试错误处理
- [ ] 优化工作流性能

**Day 19 (周四): 性能优化**
- [ ] 性能瓶颈分析
- [ ] 优化Agent处理逻辑
- [ ] 优化记忆存储结构
- [ ] 执行性能测试

**Day 20 (周五): 错误处理完善**
- [ ] 完善全局错误处理
- [ ] 添加日志记录
- [ ] 实现重试机制
- [ ] 编写错误处理文档

### 第五周: UI界面与多轮对话 🔄

**Day 21 (周一): 前端UI框架搭建**
- [ ] 选择前端技术栈（Streamlit / Gradio / React）
- [ ] 创建项目前端目录结构
- [ ] 实现基础对话界面（消息列表 + 输入框）
- [ ] 实现文件上传组件（支持PDF/DOCX/TXT）
- [ ] 对接后端API接口
- [ ] 实现消息发送和接收的基本流程

**Day 22 (周二): 意图识别与Agent路由**
- [ ] 设计意图识别逻辑（关键词/LLM分类）
- [ ] 在Coordinator中实现意图路由方法
- [ ] 实现对话上下文管理
- [ ] 测试各种指令的路由准确性

**Day 23 (周三): 多轮对话实现**
- [ ] 实现对话历史存储
- [ ] 实现上下文注入（历史对话 + 上传文件）
- [ ] 支持追问场景（解析→风险→修改建议→报告）
- [ ] 测试多轮对话的上下文连贯性

**Day 24 (周四): 结果展示与交互优化**
- [ ] 设计结构化结果展示模板
- [ ] 实现加载动画和进度显示
- [ ] 前端结果卡片、进度条、状态提示
- [ ] 测试端到端流程

**Day 25 (周五): 联调与测试**
- [ ] 前后端联调测试
- [ ] 修复联调中的bug
- [ ] 测试边界情况（空文件、超大文件）
- [ ] 编写使用说明文档

---

## 8. 依赖配置

### requirements.txt

```txt
# LangChain核心
langchain>=0.1.0
langchain-core>=0.1.0
langchain-community>=0.0.0
langgraph>=0.0.0

# MIMO模型支持
# 根据MIMO模型的API配置

# 向量数据库
chromadb>=0.4.0
sentence-transformers>=2.2.0

# 缓存和存储
redis>=5.0.0
pymongo>=4.0.0

# 文档处理
pypdf>=3.17.0
python-docx>=1.0.0
pytesseract>=0.3.10

# 数据处理
pandas>=2.0.0
numpy>=1.24.0

# 开发工具
python-dotenv>=1.0.0
pydantic>=2.0.0
```

### .env配置

```env
# MIMO模型配置
MIMO_API_KEY=your_api_key
MIMO_API_BASE=https://api.mimo.com/v1

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379

# 向量数据库配置
CHROMA_PERSIST_DIRECTORY=./chroma_db

# 日志配置
LOG_LEVEL=INFO
```

---

## 9. UI界面与多轮对话设计

### 9.1 整体交互流程

```
用户界面
┌──────────────────────────────────────────────────────────────┐
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    对话消息列表                         │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 🤖 你好！我是智能合同审查助手。                    │  │  │
│  │  │ 请上传合同文件或告诉我你需要什么帮助。              │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 👤 [上传] 劳动合同.pdf                            │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 🤖 📄 文件已解析完成                              │  │  │
│  │  │    合同类型: 劳动合同                              │  │  │
│  │  │    当事人: 张三 / XX科技有限公司                    │  │  │
│  │  │    条款数: 12条                                   │  │  │
│  │  │                                                   │  │  │
│  │  │    你想让我做什么？                                │  │  │
│  │  │    • 分析条款完整性                                │  │  │
│  │  │    • 评估风险                                      │  │  │
│  │  │    • 合规检查                                      │  │  │
│  │  │    • 生成完整报告                                  │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 👤 评估一下风险                                   │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ 🤖 ⚠️ 风险评估完成                                │  │  │
│  │  │    整体风险等级: 中等                              │  │  │
│  │  │    ┌─────────────────────────────────────────┐   │  │  │
│  │  │    │ 🔴 高风险: 2项                           │   │  │  │
│  │  │    │   • 无限责任条款                          │   │  │  │
│  │  │    │   • 自动续约无限制                        │   │  │  │
│  │  │    │ 🟡 中风险: 3项                           │   │  │  │
│  │  │    │   • 违约金比例偏高                        │   │  │  │
│  │  │    │   • 保密期限过长                          │   │  │  │
│  │  │    │   • 争议解决条款不明确                    │   │  │  │
│  │  │    └─────────────────────────────────────────┘   │  │  │
│  │  │                                                   │  │  │
│  │  │    需要我生成修改建议吗？                         │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ 📎  [文件上传]     请输入指令...           [发送]        ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 9.2 意图识别与Agent路由

用户输入通过LLM进行意图分类，路由到对应的Agent：

```python
# 意图识别规则
INTENT_ROUTES = {
    # 单Agent指令
    "解析": ["document_parser"],           # "解析这个文件"
    "分析条款": ["clause_analyst"],         # "分析条款"
    "风险": ["risk_assessor"],             # "评估风险"、"有什么风险"
    "合规": ["compliance_checker"],        # "合规检查"、"合法吗"
    "报告": ["all"],                        # "生成报告"、"完整审查"

    # 组合指令
    "修改建议": ["risk_assessor", "clause_analyst"],  # "有什么修改建议"
    "对比": ["all"],                       # "对比两份合同"
}
```

### 9.3 多轮对话上下文管理

```python
class ConversationManager:
    """对话上下文管理器"""

    def __init__(self):
        # 每个会话的上下文
        self.sessions: Dict[str, SessionContext] = {}

    def get_context(self, session_id: str) -> SessionContext:
        """获取会话上下文"""
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionContext()
        return self.sessions[session_id]


class SessionContext:
    """单个会话的上下文"""

    def __init__(self):
        self.history: List[Dict] = []          # 对话历史
        self.current_contract: str = ""         # 当前合同文本
        self.contract_type: str = ""            # 合同类型
        self.parsed_result: Dict = {}           # 解析结果缓存
        self.analysis_cache: Dict = {}          # 分析结果缓存
```

### 9.4 多轮对话示例

```
第1轮: 上传文件
  用户: [上传劳动合同.pdf]
  系统: DocumentParserAgent → 解析结果
  上下文: current_contract="...", parsed_result={...}

第2轮: 指定分析
  用户: "这个合同有什么风险？"
  系统: 意图="风险" → RiskAssessmentAgent(用parsed_result)
  上下文: analysis_cache["risk"]={...}

第3轮: 追问细节
  用户: "违约金条款具体怎么改？"
  系统: 意图="条款修改" → ClauseAnalysisAgent(针对性分析)
  上下文: 保留之前的风险结果

第4轮: 完整报告
  用户: "帮我生成完整报告"
  系统: 意图="报告" → CoordinatorAgent(所有Agent)
  上下文: 汇总所有已有的分析结果
```

### 9.5 API接口设计

```python
# 对话接口
POST /api/v1/chat
{
    "session_id": "xxx",           # 会话ID
    "message": "评估一下风险",      # 用户消息
    "file": null                   # 可选：上传文件
}

# 响应
{
    "session_id": "xxx",
    "reply": "风险评估完成...",     # AI回复
    "agent_used": "risk_assessor", # 使用的Agent
    "result": {...},               # 结构化结果
    "suggestions": [...]           # 后续操作建议
}
```

---

## 10. 总结

本系统使用LangChain框架 + 自定义BaseAgent实现智能合同审查，主要特点：

1. **模型灵活性**: 支持MIMO等非Claude模型，通过LLMFactory统一管理
2. **Agent架构**: 6个专业Agent（协调器+5个分析Agent），BaseAgent基类统一接口
3. **智能编排**: CoordinatorAgent使用LLM动态规划执行计划，支持并行/串行混合
4. **记忆系统**: SharedMemoryManager分层存储 + AgentPrivateMemory上下文压缩
5. **工具集成**: LangChain Tools + Skills双重工具体系
6. **多轮对话**: 对话上下文管理，支持追问和深入分析
7. **UI交互**: 对话式界面，文件上传 + 意图路由 + 结构化展示

开发进度：已完成Day 1-14（基础架构+核心Agent+Skills+API），待开发Day 15-25（集成测试+UI与多轮对话）。
