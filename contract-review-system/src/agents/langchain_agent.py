"""
LangChain Agent包装器 - 让BaseAgent能够使用LangChain功能
"""
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models import BaseLLM
import logging

from .base_agent import BaseAgent
from src.utils.llm_factory import get_llm
from src.utils.llm_response import extract_llm_content
from src.tools.langchain_tools import contract_tools

logger = logging.getLogger(__name__)


class LangChainAgentWrapper:
    """
    LangChain Agent包装器

    为BaseAgent提供LLM驱动的分析能力
    """

    def __init__(self, agent: BaseAgent, tools: Optional[List] = None):
        """
        初始化包装器

        Args:
            agent: 要包装的Agent实例
            tools: 可用的工具列表
        """
        self.agent = agent
        self.llm = agent.llm or get_llm()
        self.tools = tools or contract_tools
        self._conversation_history: List[Dict[str, str]] = []

    def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        与LLM对话

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            LLM响应
        """
        messages = self._build_messages(message, system_prompt)
        response = self.llm.invoke(messages)
        content = extract_llm_content(response.content)
        self._update_history(message, content)
        return content

    async def achat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        与LLM异步对话

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            LLM响应
        """
        messages = self._build_messages(message, system_prompt)
        response = await self.llm.ainvoke(messages)
        content = extract_llm_content(response.content)
        self._update_history(message, content)
        return content

    def _build_messages(self, message: str, system_prompt: Optional[str] = None):
        """构建消息列表"""
        messages = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # 添加对话历史
        for msg in self._conversation_history[-10:]:  # 保留最近10条
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))
        return messages

    def _update_history(self, user_message: str, assistant_message: str):
        """更新对话历史"""
        self._conversation_history.append({"role": "user", "content": user_message})
        self._conversation_history.append({"role": "assistant", "content": assistant_message})

    def analyze_with_tools(self, task: str, tool_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        使用工具分析任务

        Args:
            task: 分析任务描述
            tool_names: 要使用的工具名称列表

        Returns:
            分析结果
        """
        # 筛选工具
        if tool_names:
            selected_tools = [t for t in self.tools if t.name in tool_names]
        else:
            selected_tools = self.tools

        # 构建工具描述
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in selected_tools
        ])

        system_prompt = f"""你是一个专业的合同分析助手。你可以使用以下工具来帮助分析合同：

{tool_descriptions}

请根据任务需求选择合适的工具进行分析。"""

        result = self.chat(task, system_prompt)

        return {
            "agent": self.agent.name,
            "task": task,
            "result": result,
            "tools_used": [t.name for t in selected_tools],
        }

    def clear_history(self):
        """清空对话历史"""
        self._conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history.copy()


def create_llm_agent(
    agent_id: str,
    name: str,
    role: str,
    system_prompt: str,
    tools: Optional[List] = None,
    llm: Optional[BaseLLM] = None
) -> BaseAgent:
    """
    创建一个LLM驱动的Agent

    Args:
        agent_id: Agent ID
        name: Agent名称
        role: Agent角色
        system_prompt: 系统提示词
        tools: 可用工具列表
        llm: LLM实例

    Returns:
        配置好的Agent实例
    """
    from .base_agent import BaseAgent

    # 创建一个具体的Agent类
    class LLMEnabledAgent(BaseAgent):
        def __init__(self):
            super().__init__(
                agent_id=agent_id,
                name=name,
                role=role,
                llm=llm,
                description=f"LLM驱动的{role} Agent"
            )
            self.system_prompt = system_prompt
            self.wrapper = LangChainAgentWrapper(self, tools)

        async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
            """处理任务"""
            task_content = task.get("content", str(task))
            result = self.wrapper.chat(task_content, self.system_prompt)
            return {
                "agent_id": self.agent_id,
                "result": result,
                "task": task,
            }

    return LLMEnabledAgent()
