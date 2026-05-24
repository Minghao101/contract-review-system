"""
MCP Client模块 - MCP客户端实现
"""
from typing import Any, Dict, List, Optional
from .protocol import MCPRequest, MCPResponse, MCPTool
from .server import MCPServer
import logging

logger = logging.getLogger(__name__)


class MCPClient:
    """
    MCP Client实现

    用于与MCP Server通信，调用工具和访问资源
    """

    def __init__(self, server: MCPServer):
        """
        初始化MCP Client

        Args:
            server: MCP Server实例（本地模式）
        """
        self.server = server
        self._initialized = False
        self._server_info: Optional[Dict[str, Any]] = None
        self._available_tools: List[MCPTool] = []

    async def connect(self) -> bool:
        """
        连接到MCP Server

        Returns:
            是否连接成功
        """
        try:
            # 发送初始化请求
            init_request = MCPRequest(
                method="initialize",
                params={
                    "clientInfo": {
                        "name": "ContractReviewClient",
                        "version": "1.0.0"
                    }
                }
            )

            response = await self.server.handle_request(init_request)

            if response.error_info:
                logger.error(f"初始化失败: {response.error_info}")
                return False

            self._server_info = response.result
            self._initialized = True

            # 获取可用工具列表
            await self._load_tools()

            logger.info(f"连接成功: {self._server_info.get('serverInfo', {}).get('name')}")
            return True

        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    async def _load_tools(self):
        """加载服务器提供的工具列表"""
        request = MCPRequest(method="tools/list")
        response = await self.server.handle_request(request)

        if response.result and "tools" in response.result:
            self._available_tools = [
                MCPTool(**tool) for tool in response.result["tools"]
            ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if not self._initialized:
            raise RuntimeError("客户端未初始化，请先调用connect()")

        request = MCPRequest(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )

        response = await self.server.handle_request(request)

        if response.error_info:
            raise Exception(f"工具调用失败: {response.error_info}")

        # 解析返回内容
        result = response.result
        if "content" in result:
            contents = result["content"]
            if len(contents) == 1 and contents[0].get("type") == "text":
                return contents[0]["text"]
            return contents

        return result

    def list_tools(self) -> List[MCPTool]:
        """列出可用工具"""
        return self._available_tools

    def get_tool_info(self, tool_name: str) -> Optional[MCPTool]:
        """获取工具信息"""
        for tool in self._available_tools:
            if tool.name == tool_name:
                return tool
        return None

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._initialized

    @property
    def server_info(self) -> Optional[Dict[str, Any]]:
        """服务器信息"""
        return self._server_info
