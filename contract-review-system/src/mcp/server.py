"""
MCP Server模块 - MCP服务端核心实现
"""
from typing import Any, Callable, Dict, List, Optional
from .protocol import (
    MCPRequest, MCPResponse, MCPError,
    MCPTool, MCPResource
)
import logging

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server实现

    支持：
    - 工具注册和调用
    - 资源管理
    - JSON-RPC 2.0协议
    - 异步处理
    """

    def __init__(self, server_id: str, name: str, version: str = "1.0.0"):
        """
        初始化MCP Server

        Args:
            server_id: 服务器ID
            name: 服务器名称
            version: 版本号
        """
        self.server_id = server_id
        self.name = name
        self.version = version

        # 工具注册表: {tool_name: (tool_info, handler)}
        self._tools: Dict[str, tuple] = {}

        # 资源注册表: {uri: resource}
        self._resources: Dict[str, MCPResource] = {}

        # 方法处理器: {method: handler}
        self._method_handlers: Dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }

        logger.info(f"MCP Server初始化: {name} v{version}")

    def register_tool(
        self,
        tool: MCPTool,
        handler: Callable[[Dict[str, Any]], Any]
    ):
        """
        注册工具

        Args:
            tool: 工具定义
            handler: 工具处理函数
        """
        self._tools[tool.name] = (tool, handler)
        logger.info(f"注册工具: {tool.name}")

    def register_resource(self, resource: MCPResource):
        """注册资源"""
        self._resources[resource.uri] = resource
        logger.info(f"注册资源: {resource.uri}")

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        处理MCP请求

        Args:
            request: MCP请求

        Returns:
            MCP响应
        """
        logger.debug(f"收到请求: {request.method}")

        # 查找方法处理器
        handler = self._method_handlers.get(request.method)
        if handler is None:
            return MCPResponse.create_error(
                request.id,
                MCPError.METHOD_NOT_FOUND,
                f"方法未找到: {request.method}"
            )

        try:
            result = await handler(request)
            return MCPResponse.success(request.id, result)
        except Exception as e:
            logger.error(f"处理请求失败: {e}")
            return MCPResponse.create_error(
                request.id,
                MCPError.INTERNAL_ERROR,
                str(e)
            )

    async def _handle_initialize(self, request: MCPRequest) -> Dict[str, Any]:
        """处理初始化请求"""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version
            },
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False}
            }
        }

    async def _handle_tools_list(self, request: MCPRequest) -> Dict[str, Any]:
        """处理工具列表请求"""
        tools = [tool.to_dict() for tool, _ in self._tools.values()]
        return {"tools": tools}

    async def _handle_tools_call(self, request: MCPRequest) -> Dict[str, Any]:
        """处理工具调用请求"""
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if tool_name not in self._tools:
            raise ValueError(f"工具未找到: {tool_name}")

        tool, handler = self._tools[tool_name]

        try:
            result = handler(arguments)
            # 如果是协程，等待它
            if hasattr(result, '__await__'):
                result = await result
            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(result)
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"工具执行失败: {str(e)}"
                    }
                ],
                "isError": True
            }

    async def _handle_resources_list(self, request: MCPRequest) -> Dict[str, Any]:
        """处理资源列表请求"""
        resources = [r.model_dump() for r in self._resources.values()]
        return {"resources": resources}

    async def _handle_resources_read(self, request: MCPRequest) -> Dict[str, Any]:
        """处理资源读取请求"""
        uri = request.params.get("uri")
        if uri not in self._resources:
            raise ValueError(f"资源未找到: {uri}")

        resource = self._resources[uri]
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource.mime_type,
                    "text": f"资源内容: {resource.name}"
                }
            ]
        }

    async def _handle_ping(self, request: MCPRequest) -> Dict[str, Any]:
        """处理ping请求"""
        return {}

    def get_tool_info(self, tool_name: str) -> Optional[MCPTool]:
        """获取工具信息"""
        if tool_name in self._tools:
            return self._tools[tool_name][0]
        return None

    def list_tools(self) -> List[MCPTool]:
        """列出所有工具"""
        return [tool for tool, _ in self._tools.values()]
