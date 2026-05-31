# 编码规范

## 1. Python 代码规范

### 命名约定
- **模块/文件**: `snake_case.py`（如 `base_agent.py`）
- **类名**: `PascalCase`（如 `CoordinatorAgent`）
- **函数/方法**: `snake_case`（如 `process_task`）
- **常量**: `UPPER_SNAKE_CASE`（如 `REQUIRED_CLAUSES`）
- **私有属性**: `_leading_underscore`（如 `_registered_agents`）
- **受保护方法**: `_leading_underscore`（如 `_plan_with_llm`）

### 文件组织
```python
"""
模块docstring - 简要说明模块职责
"""
# 1. 标准库导入
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

# 2. 第三方库导入
from langchain_core.messages import HumanMessage, SystemMessage

# 3. 本地模块导入
from .base_agent import BaseAgent
from src.utils.llm_factory import get_llm

logger = logging.getLogger(__name__)
```

### 类定义规范
```python
class MyAgent(BaseAgent):
    """
    Agent描述
    
    职责：
    - 职责1
    - 职责2
    """
    
    def __init__(
        self,
        agent_id: str = "my_agent",
        name: str = "我的Agent",
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="my_role",
            description="Agent描述",
            **kwargs
        )
    
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务"""
        pass
```

## 2. Agent 开发规范

### 必须继承 BaseAgent
```python
from src.agents.base_agent import BaseAgent

class MyNewAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="unique_id",
            name="Agent名称",
            role="role_name",
            description="Agent描述",
            **kwargs
        )
    
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        # 实现逻辑
        return {"result": "value"}
```

### LLM 调用模式
```python
from langchain_core.messages import HumanMessage, SystemMessage

async def _analyze_with_llm(self, text: str) -> Dict[str, Any]:
    """使用LLM进行分析"""
    messages = [
        SystemMessage(content="系统提示词"),
        HumanMessage(content=f"用户输入: {text}")
    ]
    
    try:
        response = await self.llm.ainvoke(messages)
        result = self._parse_response(response.content)
        return result
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        # 正则回退
        return self._fallback_parse(text)
```

### JSON 容错处理
```python
try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

def _parse_response(self, text: str) -> Dict:
    """解析LLM响应，带容错"""
    if HAS_JSON_REPAIR:
        return json_repair.loads(text)
    # 手动修复
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 提取JSON部分
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"error": "解析失败"}
```

## 3. Skill 开发规范

### 必须继承 BaseSkill
```python
from src.skills.base_skill import BaseSkill

class MySkill(BaseSkill):
    def __init__(self):
        super().__init__(
            skill_id="my_skill",
            name="我的技能",
            description="技能描述",
            version="1.0.0"
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行技能"""
        file_path = kwargs.get("file_path")
        # 实现逻辑
        return {"result": "value"}
```

### 注册为 MCP 工具
```python
from src.skills.skill_registry import SkillRegistry
from src.mcp.server import MCPServer

# 创建 MCP Server
mcp_server = MCPServer("server_id", "Server名称")

# 创建注册器
registry = SkillRegistry(mcp_server)

# 注册技能
registry.register_skill(MySkill(), tool_name="my_tool")
```

## 4. 配置规范

### 使用 Pydantic Settings
```python
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # 字段使用 Field 定义
    MY_CONFIG: str = Field(default="default_value", description="配置说明")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

## 5. 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# 使用方式
logger.info(f"初始化完成: {name}")
logger.warning(f"配置缺失: {config_name}")
logger.error(f"处理失败: {error}")
logger.debug(f"调试信息: {data}")
```

## 6. 异步编程规范

- 所有 Agent 的 `process()` 方法必须是 `async`
- 使用 `await` 调用异步方法
- 使用 `asyncio.gather()` 实现并行执行
- 使用 `try/except` 包裹异步调用

## 7. 测试规范

- 测试文件命名: `test_<module>.py`
- 测试类命名: `Test<ClassName>`
- 测试方法命名: `test_<method_name>_<scenario>`
- 使用 `pytest` 框架
- 集成测试放在 `tests/integration/`
- 单元测试放在 `tests/unit/`
