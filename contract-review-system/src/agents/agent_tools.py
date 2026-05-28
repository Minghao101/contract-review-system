"""
Agent工具集成模块 - 让Agent能够使用Skills和MCP工具
"""
from typing import Any, Dict, List, Optional
import logging

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from src.skills.skill_registry import SkillRegistry
from src.skills import document_skills, legal_skills, risk_skills, report_skills

logger = logging.getLogger(__name__)


class AgentTools:
    """
    Agent工具管理器

    提供工具注册、调用和管理功能
    """

    def __init__(self, skill_registry: Optional[SkillRegistry] = None):
        """
        初始化工具管理器

        Args:
            skill_registry: Skills注册器
        """
        self.skill_registry = skill_registry or SkillRegistry()
        self._langchain_tools = []

        # 注册Skills
        self._register_document_skills()
        self._register_legal_skills()
        self._register_risk_skills()
        self._register_report_skills()

    def _register_document_skills(self):
        """注册文档处理Skills"""
        for skill in document_skills:
            self.skill_registry.register_skill(skill)

    def _register_legal_skills(self):
        """注册法律分析Skills"""
        for skill in legal_skills:
            self.skill_registry.register_skill(skill)

    def _register_risk_skills(self):
        """注册风险管理Skills"""
        for skill in risk_skills:
            self.skill_registry.register_skill(skill)

    def _register_report_skills(self):
        """注册报告生成Skills"""
        for skill in report_skills:
            self.skill_registry.register_skill(skill)

    def get_langchain_tools(self) -> List:
        """获取LangChain工具列表"""
        return self._langchain_tools

    def create_langchain_tool(self, skill_id: str):
        """
        将Skill转换为LangChain工具

        Args:
            skill_id: Skill ID
        """
        skill = self.skill_registry.get_skill(skill_id)
        if not skill:
            logger.warning(f"Skill未找到: {skill_id}")
            return

        @tool
        async def skill_tool(file_path: str = "", file_bytes: str = "") -> str:
            """
            {description}

            Args:
                file_path: 文件路径（可选）
                file_bytes: 文件字节Base64（可选）
            """
            result = await skill.execute(
                file_path=file_path,
                file_bytes=file_bytes
            )
            return str(result)

        # 设置工具名称和描述
        skill_tool.name = skill.skill_id
        skill_tool.description = skill.description

        self._langchain_tools.append(skill_tool)
        logger.info(f"LangChain工具已创建: {skill.name}")

    def create_all_langchain_tools(self):
        """创建所有可用的LangChain工具"""
        for skill in self.skill_registry.list_skills():
            self.create_langchain_tool(skill["skill_id"])

    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        return await self.skill_registry.execute_tool(tool_name, **kwargs)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        return self.skill_registry.list_skills()


class AgentWithTools:
    """
    带工具能力的Agent基类

    为Agent提供工具调用能力
    """

    def __init__(self, agent, tools: Optional[AgentTools] = None):
        """
        初始化

        Args:
            agent: Agent实例
            tools: 工具管理器
        """
        self.agent = agent
        self.tools = tools or AgentTools()
        self._conversation_history = []

    async def chat_with_tools(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        use_tools: bool = True
    ) -> str:
        """
        与LLM对话（支持工具调用）

        Args:
            message: 用户消息
            system_prompt: 系统提示词
            use_tools: 是否使用工具

        Returns:
            响应内容
        """
        messages = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        # 添加对话历史
        for msg in self._conversation_history[-10:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))

        # 调用LLM
        response = self.agent.llm.invoke(messages)

        # 更新对话历史
        self._conversation_history.append({"role": "user", "content": message})
        self._conversation_history.append({"role": "assistant", "content": response.content})

        return response.content

    def clear_history(self):
        """清空对话历史"""
        self._conversation_history = []
