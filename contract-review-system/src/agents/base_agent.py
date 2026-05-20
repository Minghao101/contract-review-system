"""
基础Agent模块 - 定义所有Agent的基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
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
        description: str = ""
    ):
        """
        初始化Agent

        Args:
            agent_id: Agent唯一标识符
            name: Agent名称
            role: Agent角色
            llm: LLM实例 (可选)
            description: Agent描述
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
