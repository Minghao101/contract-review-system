# 智能合同审查系统 - 编码规范

## 1. 通用规范

### 1.1 语言与风格

- **语言**: Python 3.10+
- **异步优先**: 所有 Agent 方法和 API 端点使用 `async/await`
- **类型注解**: 所有函数参数和返回值必须有类型注解
- **文档字符串**: 使用 Google 风格 docstring

### 1.2 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `coordinator_agent.py` |
| 类 | PascalCase | `CoordinatorAgent`, `BaseSkill` |
| 函数/方法 | snake_case | `process()`, `_plan_execution()` |
| 常量 | UPPER_SNAKE_CASE | `MEMORY_LAYER_CONTEXT` |
| 私有方法 | 前缀 `_` | `_find_agent_by_role()`, `_aggregate_results()` |
| Agent ID | snake_case | `"document_parser"`, `"risk_assessor"` |
| Agent role | snake_case | `"coordinator"`, `"clause_analyst"` |

### 1.3 文件组织

```python
# 1. 标准库导入
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

# 2. 第三方库导入
from langchain_core.messages import HumanMessage, SystemMessage

# 3. 本地模块导入
from .base_agent import BaseAgent
from .communication import MessageBus, AgentMessage, MessageType
from src.utils.llm_factory import get_llm

# 4. 日志
logger = logging.getLogger(__name__)
```

## 2. Agent 开发规范

### 2.1 继承 BaseAgent

所有新 Agent 必须：

```python
from src.agents.base_agent import BaseAgent

class MyNewAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str = "my_agent",
        name: str = "我的Agent",
        llm=None,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="my_role",          # 用于 CoordinatorAgent 路由匹配
            description="Agent 功能描述",
            llm=llm,
            **kwargs
        )

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务"""
        self.set_running(True)
        try:
            # 业务逻辑
            result = {}
            return result
        except Exception as e:
            logger.error(f"处理失败: {e}")
            return {"error": str(e)}
        finally:
            self.set_running(False)
```

### 2.2 Agent 注册

新 Agent 创建后必须在两个地方注册：

1. **TaskManager** (`src/api/task_manager.py`):
```python
self._coordinator.register_agent(MyNewAgent())
```

2. **CoordinatorAgent 默认计划** (`_get_default_plan()`)（如需参与自动调度）

### 2.3 LLM 调用规范

```python
from langchain_core.messages import HumanMessage, SystemMessage
from src.utils.llm_factory import get_llm

# ✅ 正确：使用 get_llm() 获取 LLM
llm = get_llm()
response = await llm.ainvoke([
    SystemMessage(content="系统提示"),
    HumanMessage(content="用户输入")
])

# ❌ 错误：直接实例化模型
# llm = ChatOpenAI(model="xxx")
```

### 2.4 错误处理

```python
async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
    self.set_running(True)
    start_time = datetime.now()
    try:
        # 业务逻辑
        result = await self._do_work(task)
        return result
    except Exception as e:
        logger.error(f"Agent [{self.agent_id}] 处理失败: {e}")
        return {"error": str(e), "agent_id": self.agent_id}
    finally:
        self.set_running(False)
```

## 3. Skill 开发规范

### 3.1 继承 BaseSkill

```python
from src.skills.base_skill import BaseSkill

class MyNewSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            skill_id="my_skill",
            name="我的Skill",
            description="Skill 功能描述"
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行 Skill 逻辑"""
        # 具体实现
        return {"result": "..."}
```

### 3.2 Skill 注册

在 [`src/skills/__init__.py`](contract-review-system/src/skills/__init__.py) 中导入并在 [`SkillRegistry`](contract-review-system/src/skills/skill_registry.py) 中注册。

### 3.3 Skill 分类

| 分类 | 目录 | 职责 |
|------|------|------|
| document | `src/skills/document/` | 文档解析（PDF/DOCX/OCR） |
| legal | `src/skills/legal/` | 法律分析（条款/法规/案例） |
| risk | `src/skills/risk/` | 风险管理（识别/量化/缓解） |
| report | `src/skills/report/` | 报告生成（综合/可视化/导出） |

## 4. MCP 工具开发规范

### 4.1 定义工具

```python
from src.mcp.protocol import MCPTool

# 定义工具
tool = MCPTool(
    name="my_tool",
    description="工具描述",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"}
        },
        "required": ["param1"]
    }
)

# 定义处理函数
async def my_handler(arguments: Dict[str, Any]) -> Any:
    # 工具逻辑
    return {"result": "..."}

# 注册到 MCP Server
server.register_tool(tool, my_handler)
```

## 5. 配置管理规范

### 5.1 新增配置项

在 [`config/settings.py`](contract-review-system/config/settings.py) 的 `Settings` 类中添加：

```python
class Settings(BaseSettings):
    # 新配置项（必须有默认值和 description）
    MY_NEW_CONFIG: str = Field(default="default_value", description="配置说明")
```

### 5.2 环境变量覆盖

在 `.env` 文件中设置（与配置项同名，大写）：

```env
MY_NEW_CONFIG=actual_value
```

## 6. 日志规范

```python
import logging

# 模块级 logger
logger = logging.getLogger(__name__)

# 使用方式
logger.info(f"开始处理任务，文本长度: {len(contract_text)}")
logger.warning(f"LLM规划失败，使用默认计划: {e}")
logger.error(f"执行任务失败 [{task_name}]: {e}")
logger.debug(f"执行计划: {json.dumps(plan, ensure_ascii=False)}")
```

## 7. 测试规范

### 7.1 文件位置

- 单元测试: `tests/test_*.py`
- 集成测试: `tests/integration/`
- 测试文件命名: `test_{模块名}.py`

### 7.2 测试结构

```python
import pytest
from src.agents.my_agent import MyAgent

class TestMyAgent:
    """MyAgent 测试类"""

    @pytest.fixture
    def agent(self):
        return MyAgent()

    @pytest.mark.asyncio
    async def test_process_success(self, agent):
        """测试正常处理流程"""
        task = {"contract_text": "...", "contract_type": "劳动合同"}
        result = await agent.process(task)
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_process_empty_input(self, agent):
        """测试空输入处理"""
        result = await agent.process({})
        assert "error" in result
```

### 7.3 运行测试

```bash
cd contract-review-system
pytest tests/ -v
pytest tests/test_agents.py -v
```
