"""
MCP测试模块
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from src.mcp.protocol import MCPRequest, MCPResponse, MCPTool, MCPError
from src.mcp.server import MCPServer
from src.mcp.client import MCPClient


def test_protocol():
    """测试MCP协议"""
    print("测试MCP协议...")

    # 测试请求创建
    request = MCPRequest(
        method="tools/list",
        params={"filter": "all"}
    )
    assert request.jsonrpc == "2.0"
    assert request.method == "tools/list"

    # 测试响应创建
    response = MCPResponse.success(request.id, {"tools": []})
    assert response.result == {"tools": []}
    assert response.error_info is None

    # 测试错误响应
    error_response = MCPResponse.create_error(
        request.id,
        MCPError.METHOD_NOT_FOUND,
        "方法未找到"
    )
    assert error_response.error_info["code"] == MCPError.METHOD_NOT_FOUND

    # 测试工具定义
    tool = MCPTool(
        name="test_tool",
        description="测试工具",
        input_schema={"type": "object", "properties": {"input": {"type": "string"}}}
    )
    tool_dict = tool.to_dict()
    assert tool_dict["name"] == "test_tool"

    print("MCP协议测试通过！")
    return True


def test_server():
    """测试MCP Server"""
    print("测试MCP Server...")

    server = MCPServer(
        server_id="test_server",
        name="Test Server",
        version="1.0.0"
    )

    # 注册测试工具
    def echo_handler(args):
        return f"Echo: {args.get('message', '')}"

    echo_tool = MCPTool(
        name="echo",
        description="回声工具",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}}
        }
    )
    server.register_tool(echo_tool, echo_handler)

    # 测试工具列表
    assert len(server.list_tools()) == 1
    assert server.list_tools()[0].name == "echo"

    print("MCP Server测试通过！")
    return True


async def test_server_async():
    """测试MCP Server异步操作"""
    print("测试MCP Server异步操作...")

    server = MCPServer(
        server_id="test_server_async",
        name="Test Server Async"
    )

    # 注册工具
    def add_handler(args):
        return args.get("a", 0) + args.get("b", 0)

    add_tool = MCPTool(
        name="add",
        description="加法工具",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"}
            }
        }
    )
    server.register_tool(add_tool, add_handler)

    # 测试初始化
    init_request = MCPRequest(method="initialize", params={})
    init_response = await server.handle_request(init_request)
    assert init_response.result is not None
    assert "serverInfo" in init_response.result

    # 测试工具列表
    list_request = MCPRequest(method="tools/list")
    list_response = await server.handle_request(list_request)
    assert len(list_response.result["tools"]) == 1

    # 测试工具调用
    call_request = MCPRequest(
        method="tools/call",
        params={"name": "add", "arguments": {"a": 5, "b": 3}}
    )
    call_response = await server.handle_request(call_request)
    assert "content" in call_response.result
    assert call_response.result["content"][0]["text"] == "8"

    # 测试ping
    ping_request = MCPRequest(method="ping")
    ping_response = await server.handle_request(ping_request)
    assert ping_response.result == {}

    print("MCP Server异步操作测试通过！")
    return True


async def test_client():
    """测试MCP Client"""
    print("测试MCP Client...")

    # 创建Server
    server = MCPServer(server_id="test_server", name="Test Server")

    # 注册工具
    def greet_handler(args):
        name = args.get("name", "World")
        return f"Hello, {name}!"

    greet_tool = MCPTool(
        name="greet",
        description="问候工具",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}}
        }
    )
    server.register_tool(greet_tool, greet_handler)

    # 创建Client并连接
    client = MCPClient(server)
    connected = await client.connect()

    assert connected == True
    assert client.is_connected == True

    # 测试工具列表
    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "greet"

    # 测试工具调用
    result = await client.call_tool("greet", {"name": "MCP"})
    assert result == "Hello, MCP!"

    print("MCP Client测试通过！")
    return True


async def test_error_handling():
    """测试错误处理"""
    print("测试错误处理...")

    server = MCPServer(server_id="test_server", name="Test Server")

    # 测试未知方法
    request = MCPRequest(method="unknown/method")
    response = await server.handle_request(request)
    assert response.error_info is not None
    assert response.error_info["code"] == MCPError.METHOD_NOT_FOUND

    # 测试未知工具
    call_request = MCPRequest(
        method="tools/call",
        params={"name": "unknown_tool", "arguments": {}}
    )
    call_response = await server.handle_request(call_request)
    # 工具不存在会抛出异常，被转换为错误响应
    assert call_response.error_info is not None

    print("错误处理测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始运行MCP测试")
    print("=" * 50)

    tests = [
        test_protocol(),
        test_server(),
        asyncio.run(test_server_async()),
        asyncio.run(test_client()),
        asyncio.run(test_error_handling()),
    ]

    passed = sum(1 for t in tests if t)

    print("=" * 50)
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 50)

    return passed == len(tests)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
