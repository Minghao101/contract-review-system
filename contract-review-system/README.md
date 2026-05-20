# 智能合同审查系统

基于LangChain多Agent协作的智能合同审查系统，支持多种合同类型的自动化审查。

## 项目特性

- **多Agent协作**: 5个专业Agent协同工作，提高审查效率
- **LangChain框架**: 使用LangChain + LangGraph实现Agent编排
- **共享记忆系统**: Agent间共享中间结果，避免重复计算
- **可扩展架构**: 支持新增Agent和工具，易于扩展

## 技术栈

- **LLM**: MIMO模型 (可配置)
- **Agent框架**: LangChain + LangGraph
- **记忆系统**: LangChain Memory + Redis + ChromaDB
- **工具系统**: LangChain Tools
- **向量数据库**: ChromaDB
- **缓存**: Redis

## 项目结构

```
contract-review-system/
├── src/
│   ├── agents/           # Agent实现
│   ├── memory/           # 记忆系统
│   ├── tools/            # LangChain Tools
│   ├── workflow/         # LangGraph工作流
│   └── utils/            # 工具函数
├── tests/                # 测试代码
├── config/               # 配置文件
├── data/                 # 数据文件
├── docs/                 # 文档
├── requirements.txt      # 依赖列表
└── README.md             # 项目说明
```

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/Mac)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑.env文件，填入必要的配置
# LLM_API_KEY=your_api_key_here
```

### 3. 启动Redis (可选)

```bash
# 使用Docker启动Redis
docker run -d -p 6379:6379 redis:alpine
```

### 4. 运行测试

```bash
pytest tests/
```

## Agent角色

### 1. 协调器Agent (Coordinator Agent)
- 任务调度和结果汇总
- 工作流控制

### 2. 合同解析Agent (Document Parser Agent)
- 文档预处理
- 结构化提取

### 3. 条款分析Agent (Clause Analysis Agent)
- 条款深度分析
- 歧义检测

### 4. 风险评估Agent (Risk Assessment Agent)
- 风险识别和量化
- 缓解建议生成

### 5. 合规检查Agent (Compliance Checker Agent)
- 法规合规检查
- 必备条款验证

## 支持的合同类型

- 劳动合同
- 采购合同
- 租赁合同
- 技术合同
- 服务合同

## 开发计划

详见 [daily_plan.md](daily_plan.md)

## 许可证

MIT License
