"""
Skills注册器 - 将Skills注册为MCP工具
"""
from typing import Any, Callable, Dict, List, Optional
import logging

from src.mcp.server import MCPServer
from src.mcp.protocol import MCPTool
from .base_skill import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Skills注册器

    将Skills转换为MCP工具并注册到MCP Server
    """

    def __init__(self, mcp_server: Optional[MCPServer] = None):
        """
        初始化Skills注册器

        Args:
            mcp_server: MCP Server实例（可选）
        """
        self.mcp_server = mcp_server
        self._skills: Dict[str, BaseSkill] = {}
        self._tool_names: Dict[str, str] = {}  # tool_name -> skill_id

    def register_skill(self, skill: BaseSkill, tool_name: Optional[str] = None):
        """
        注册Skill

        Args:
            skill: Skill实例
            tool_name: MCP工具名称（可选，默认使用skill_id）
        """
        self._skills[skill.skill_id] = skill
        tool_name = tool_name or skill.skill_id
        self._tool_names[tool_name] = skill.skill_id

        # 如果有MCP Server，注册为MCP工具
        if self.mcp_server:
            self._register_as_mcp_tool(skill, tool_name)

        logger.info(f"Skill已注册: {skill.name} -> {tool_name}")

    def _register_as_mcp_tool(self, skill: BaseSkill, tool_name: str):
        """将Skill注册为MCP工具"""
        # 创建MCP工具定义
        mcp_tool = MCPTool(
            name=tool_name,
            description=skill.description,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "file_bytes": {
                        "type": "string",
                        "description": "文件字节（Base64编码）"
                    },
                },
            }
        )

        # 创建工具处理函数
        async def handler(args: Dict[str, Any]) -> Any:
            return await skill.execute(**args)

        # 注册到MCP Server
        self.mcp_server.register_tool(mcp_tool, handler)

    def unregister_skill(self, skill_id: str):
        """取消注册Skill"""
        if skill_id in self._skills:
            del self._skills[skill_id]
            # 移除对应的tool_name映射
            tool_names_to_remove = [
                name for name, sid in self._tool_names.items()
                if sid == skill_id
            ]
            for name in tool_names_to_remove:
                del self._tool_names[name]
            logger.info(f"Skill已取消注册: {skill_id}")

    def get_skill(self, skill_id: str) -> Optional[BaseSkill]:
        """获取Skill"""
        return self._skills.get(skill_id)

    def get_skill_by_tool_name(self, tool_name: str) -> Optional[BaseSkill]:
        """通过工具名称获取Skill"""
        skill_id = self._tool_names.get(tool_name)
        if skill_id:
            return self._skills.get(skill_id)
        return None

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有Skills"""
        return [skill.get_info() for skill in self._skills.values()]

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tool_names.keys())

    async def execute_skill(self, skill_id: str, **kwargs) -> Dict[str, Any]:
        """
        执行Skill

        Args:
            skill_id: Skill ID
            **kwargs: Skill参数

        Returns:
            执行结果
        """
        skill = self._skills.get(skill_id)
        if not skill:
            return {"error": f"Skill未找到: {skill_id}"}

        if not skill.is_enabled:
            return {"error": f"Skill已禁用: {skill_id}"}

        return await skill.execute(**kwargs)

    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        通过工具名称执行

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        skill = self.get_skill_by_tool_name(tool_name)
        if not skill:
            return {"error": f"工具未找到: {tool_name}"}

        return await skill.execute(**kwargs)
