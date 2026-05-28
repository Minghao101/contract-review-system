# 智能合同审查系统 - 开发指南

## 1. 新增 Agent 开发流程

### 步骤 1: 创建 Agent 文件

在 `src/agents/` 下创建新文件，例如 `my_agent.py`：

```python
"""
我的新Agent模块 - 功能描述
"""
import logging
from typing import Any, Dict, Optional

from .base_agent import BaseAgent
from src.utils.llm_factory import get_llm

logger = logging.getLogger(__name__)


class MyNewAgent(BaseAgent):
    """
    新Agent

    职责：
    - 职责1
    - 职责2
    """

    def __init__(
        self,
        agent_id: str = "my_new",
        name: str = "新Agent",
        llm=None,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="my_new_role",
            description="新Agent功能描述",
            llm=llm,
            **kwargs
        )

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务"""
        self.set_running(True)
        try:
            contract_text = task.get("contract_text", "")
            if not contract_text:
                return {"error": "合同文本不能为空"}

            # 1. 调用 LLM 分析
            result = await self._analyze(contract_text, task)

            # 2. 返回结构化结果
            return {
                "my_result": result,
                "status": "completed"
            }
        except Exception as e:
            logger.error(f"MyNewAgent 处理失败: {e}")
            return {"error": str(e)}
        finally:
            self.set_running(False)

    async def _analyze(self, text: str, task: Dict) -> Dict:
        """核心分析逻辑"""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content="你是一个专业的合同分析专家..."),
            HumanMessage(content=f"请分析以下合同：\n{text[:2000]}")
        ]

        response = await self.llm.ainvoke(messages)
        return {"analysis": response.content}
```

### 步骤 2: 在 `__init__.py` 中导出

在 `src/agents/__init__.py` 中添加：

```python
from .my_agent import MyNewAgent
```

### 步骤 3: 在 TaskManager 中注册

在 `src/api/task_manager.py` 的 `__init__` 方法中：

```python
from src.agents.my_agent import MyNewAgent

class TaskManager:
    def __init__(self):
        self._coordinator = CoordinatorAgent()
        # ... 其他 Agent
        self._coordinator.register_agent(MyNewAgent())
```

### 步骤 4: 配置 CoordinatorAgent 调度

如果新 Agent 需要参与自动调度，在 `coordinator_agent.py` 的 `_get_default_plan()` 中添加任务步骤。

### 步骤 5: 编写测试

在 `tests/test_agents.py` 中添加测试用例。

---

## 2. 新增 Skill 开发流程

### 步骤 1: 确定 Skill 分类

| 分类 | 目录 | 用途 |
|------|------|------|
| document | `src/skills/document/` | 文档处理 |
| legal | `src/skills/legal/` | 法律分析 |
| risk | `src/skills/risk/` | 风险管理 |
| report | `src/skills/report/` | 报告生成 |

### 步骤 2: 创建 Skill 文件

在对应分类目录下创建新文件：

```python
"""
我的新Skill模块
"""
from typing import Any, Dict
from src.skills.base_skill import BaseSkill


class MyNewSkill(BaseSkill):
    """新Skill描述"""

    def __init__(self):
        super().__init__(
            skill_id="my_new_skill",
            name="新Skill",
            description="Skill功能描述"
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行Skill逻辑"""
        # 具体实现
        return {"result": "执行结果"}
```

### 步骤 3: 在 SkillRegistry 中注册

在 `src/skills/skill_registry.py` 中注册：

```python
from .document.my_new_skill import MyNewSkill

class SkillRegistry:
    def __init__(self):
        # 注册 Skill
        self._skills["my_new_skill"] = MyNewSkill()
```

---

## 3. 新增 MCP 工具开发流程

### 步骤 1: 定义工具

在 `src/mcp/protocol.py` 中确认 `MCPTool` 结构（已定义）。

### 步骤 2: 创建工具处理器

在 `src/mcp/` 下或专门的工具模块中：

```python
from src.mcp.protocol import MCPTool, MCPRequest, MCPResponse
from src.mcp.server import MCPServer

def register_my_tools(server: MCPServer):
    """注册自定义工具到 MCP Server"""

    tool = MCPTool(
        name="my_mcp_tool",
        description="工具描述",
        inputSchema={
            "type": "object",
            "properties": {
                "input_text": {
                    "type": "string",
                    "description": "输入文本"
                }
            },
            "required": ["input_text"]
        }
    )

    async def handler(arguments: dict) -> str:
        input_text = arguments.get("input_text", "")
        # 工具逻辑
        return f"处理结果: {input_text}"

    server.register_tool(tool, handler)
```

### 步骤 3: 在 MCP Server 启动时注册

在应用启动时调用注册函数。

---

## 4. 新增 API 端点开发流程

### 步骤 1: 在路由中定义

在 `src/api/routes.py` 中添加：

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class MyRequest(BaseModel):
    """请求模型"""
    contract_text: str
    options: dict = {}

@router.post("/my-endpoint")
async def my_endpoint(request: MyRequest):
    """新端点描述"""
    try:
        # 调用 TaskManager 或直接调用 Agent
        result = await task_manager.process(request)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 步骤 2: 在 main.py 中挂载

在 `src/api/main.py` 中：

```python
from .routes import router as my_router
app.include_router(my_router, prefix="/api/v1")
```

---

## 5. 修改现有 Agent 的流程

### 5.1 添加新方法

```python
class ExistingAgent(BaseAgent):
    # 新方法（私有方法以 _ 开头）
    async def _new_analysis_method(self, data: Dict) -> Dict:
        """新分析方法"""
        # 实现
        return result

    # 在 process() 中调用
    async def process(self, task):
        # ... 现有逻辑
        new_result = await self._new_analysis_method(data)
        return {**existing_result, **new_result}
```

### 5.2 修改输出格式

修改 Agent 的 `process()` 返回值时，需要同步更新：

1. `coordinator_agent.py` 中的 `_aggregate_results()` — 汇总逻辑
2. `report_generator_agent.py` — 报告生成逻辑
3. 相关测试用例

### 5.3 添加新工具

在 Agent 的 `_create_tools()` 方法中添加新工具定义。

---

## 6. 常见开发场景

### 场景 1: 添加新的合同类型

1. 在 `config/settings.py` 的 `CONTRACT_TYPES` 列表中添加新类型
2. 在 `MANDATORY_CLAUSES` 字典中添加该类型的必备条款
3. 在 `ComplianceCheckerAgent` 中更新合规规则（如需要）
4. 添加测试用例

### 场景 2: 添加新的风险类别

1. 在 `RiskAssessmentAgent` 的风险规则库中添加新类别
2. 在 `RiskScorerSkill` 中添加对应的评分权重
3. 在 `MitigationSuggesterSkill` 中添加缓解模板
4. 更新测试用例

### 场景 3: 优化 Agent 性能

1. 使用 `asyncio.gather()` 并行处理独立任务
2. 缓存 LLM 调用结果（使用 `private_memory`）
3. 减少不必要的 LLM 调用（使用规则回退）
4. 使用 Map-Reduce 处理长文本

### 场景 4: 调试 Agent 问题

1. 检查日志输出（`logger` 模块）
2. 查看 Agent 状态（`agent.get_status()`）
3. 检查 MessageBus 消息（`communication.py`）
4. 验证输入数据格式

---

## 7. 依赖管理

### 安装新依赖

```bash
cd contract-review-system
pip install new-package
pip freeze > requirements.txt
```

### 核心依赖版本

| 包 | 版本 | 用途 |
|----|------|------|
| langchain | >=0.1.0 | Agent 框架 |
| langgraph | >=0.0.0 | 工作流编排 |
| fastapi | >=0.100.0 | API 框架 |
| pydantic | >=2.0.0 | 数据验证 |
| redis | >=5.0.0 | 缓存和消息 |
| chromadb | >=0.4.0 | 向量数据库 |

---

## 8. Git 工作流

### 分支策略

- `main` — 生产分支
- `develop` — 开发分支
- `feature/*` — 功能分支
- `fix/*` — 修复分支

### 提交规范

```
<type>(<scope>): <description>

类型: feat / fix / docs / style / refactor / test / chore
范围: agents / skills / mcp / api / memory / config
```

示例：
```
feat(agents): 添加 MyNewAgent 支持新功能
fix(api): 修复文件上传超时问题
docs(readme): 更新部署说明
```

