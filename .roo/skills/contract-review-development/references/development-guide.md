# 开发指南

## 1. 环境搭建

```bash
# 进入项目目录
cd contract-review-system

# 创建虚拟环境
python -m venv .venv

# 激活环境 (Windows)
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 等配置
```

## 2. 添加新 Agent

### 步骤
1. 在 `src/agents/` 创建新文件 `my_agent.py`
2. 继承 `BaseAgent`，实现 `process()` 方法
3. 在 `src/agents/__init__.py` 导出
4. 在 `task_manager.py` 中注册
5. 编写测试 `tests/test_my_agent.py`

### 模板
```python
"""我的Agent模块"""
from typing import Any, Dict
import logging
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

class MyAgent(BaseAgent):
    """我的Agent"""
    
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="my_agent",
            name="我的Agent",
            role="my_role",
            description="Agent描述",
            **kwargs
        )
    
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务"""
        self.set_running(True)
        try:
            # 实现逻辑
            result = {}
            return result
        except Exception as e:
            logger.error(f"处理失败: {e}")
            return {"error": str(e)}
        finally:
            self.set_running(False)
```

## 3. 添加新 Skill

### 步骤
1. 在 `src/skills/<category>/` 创建新文件
2. 继承 `BaseSkill`，实现 `execute()` 方法
3. 在对应 `__init__.py` 导出
4. 在应用启动时注册到 `SkillRegistry`
5. 编写测试

### 模板
```python
"""我的Skill模块"""
from typing import Any, Dict
import logging
from src.skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)

class MySkill(BaseSkill):
    """我的Skill"""
    
    def __init__(self):
        super().__init__(
            skill_id="my_skill",
            name="我的Skill",
            description="Skill描述",
            version="1.0.0"
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行Skill"""
        logger.info(f"执行Skill: {self.name}")
        # 实现逻辑
        return {"result": "value"}
```

## 4. 添加新合同类型

### 步骤
1. 在 `config/settings.py` 的 `CONTRACT_TYPES` 添加类型
2. 在 `MANDATORY_CLAUSES` 添加必备条款
3. 在 `ComplianceCheckerAgent` 的 `REQUIRED_CLAUSES` 添加检查规则
4. 编写对应的测试用例

## 5. 修改 LLM 配置

### 切换提供商
编辑 `config/settings.py`：
```python
LLM_PROVIDER: str = "openai"  # anthropic / openai / ollama
LLM_MODEL: str = "gpt-4"
LLM_API_BASE: Optional[str] = "https://api.openai.com/v1"
```

### 使用本地模型
```python
LLM_PROVIDER: str = "ollama"
LLM_MODEL: str = "llama2"
# 无需 API Key
```

## 6. 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_agents.py

# 运行集成测试
pytest tests/integration/

# 运行并显示覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 7. 启动服务

```bash
# 启动 API 服务
cd contract-review-system
python -m src.api.main

# 或使用 uvicorn
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## 8. API 使用示例

### 异步审查
```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{"contract_text": "合同内容...", "contract_type": "service"}'
```

### 同步审查
```bash
curl -X POST http://localhost:8000/api/v1/review/sync \
  -H "Content-Type: application/json" \
  -d '{"contract_text": "合同内容...", "contract_type": "service"}'
```

### 查询任务状态
```bash
curl http://localhost:8000/api/v1/tasks/{task_id}
```

## 9. 调试技巧

### 查看 Agent 状态
```python
from src.agents.coordinator_agent import CoordinatorAgent

coordinator = CoordinatorAgent()
# 注册 Agent 后
agents_status = coordinator.get_registered_agents()
print(agents_status)
```

### 查看共享记忆
```python
from src.memory.shared_memory import SharedMemoryManager

memory = SharedMemoryManager(contract_id="test")
# 读取各层数据
context = memory.read("contract_text", MemoryLayer.CONTEXT)
analysis = memory.read("clause_analysis", MemoryLayer.ANALYSIS)
```

### 查看 MCP 工具列表
```python
from src.mcp.server import MCPServer

server = MCPServer("test", "Test")
# 注册工具后
tools = server._tools.keys()
print(list(tools))
```

## 10. 常见问题

### Q: LLM 调用超时？
A: 检查网络连接和 API 配置，增大 `AGENT_TIMEOUT` 配置。

### Q: JSON 解析失败？
A: 确保安装了 `json_repair` 库：`pip install json_repair`。系统会自动使用正则回退。

### Q: Agent 之间数据如何共享？
A: 通过 `SharedMemoryManager` 分层存储，Agent 写入对应层，其他 Agent 可读取。

### Q: 如何添加新的 MCP 工具？
A: 创建 Skill → 继承 BaseSkill → 通过 SkillRegistry 注册 → 自动转换为 MCP 工具。
