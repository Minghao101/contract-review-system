"""
基础Agent模块 - 定义所有Agent的基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from langchain_core.language_models import BaseLLM

from src.utils.llm_factory import get_llm


class BaseAgent(ABC):
    """
    Agent基类

    所有专业Agent都应继承此类并实现抽象方法
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        llm: Optional[BaseLLM] = None,
        description: str = "",
        tools: Optional[List] = None
    ):
        """
        初始化Agent

        Args:
            agent_id: Agent唯一标识符
            name: Agent名称
            role: Agent角色
            llm: LLM实例 (可选)
            description: Agent描述
            tools: 可用工具列表 (可选)
        """
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.description = description
        self.llm = llm or get_llm()

        # Agent状态
        self.is_running = False
        self.created_at = datetime.now()
        self.last_active_at = datetime.now()

        # 私有记忆
        self.private_memory: Dict[str, Any] = {}

        # LangChain Agent包装器（延迟初始化）
        self._wrapper = None
        self._tools = tools

    @property
    def wrapper(self):
        """获取LangChain Agent包装器（延迟初始化）"""
        if self._wrapper is None:
            from .langchain_agent import LangChainAgentWrapper
            self._wrapper = LangChainAgentWrapper(self, self._tools)
        return self._wrapper

    async def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        与LLM异步对话

        Args:
            message: 用户消息
            system_prompt: 系统提示词

        Returns:
            LLM响应
        """
        return await self.wrapper.achat(message, system_prompt)

    def clear_history(self):
        """清空对话历史"""
        if self._wrapper is not None:
            self._wrapper.clear_history()

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        if self._wrapper is not None:
            return self._wrapper.get_history()
        return []

    @abstractmethod
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务 (抽象方法)

        Args:
            task: 任务数据

        Returns:
            处理结果
        """
        pass

    def update_activity(self):
        """更新Agent活跃时间"""
        self.last_active_at = datetime.now()

    def set_running(self, is_running: bool):
        """设置Agent运行状态"""
        self.is_running = is_running
        self.update_activity()

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "is_running": self.is_running,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, name={self.name}, role={self.role})"
