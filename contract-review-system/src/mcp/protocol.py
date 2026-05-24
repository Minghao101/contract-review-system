"""
MCP协议模块 - 基于JSON-RPC 2.0的MCP协议实现
"""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class MCPMessageType(str, Enum):
    """MCP消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


class MCPTool(BaseModel):
    """MCP工具定义"""
    name: str = Field(description="工具名称")
    description: str = Field(description="工具描述")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="输入参数JSON Schema"
    )
    output_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="输出参数JSON Schema"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema
        }


class MCPResource(BaseModel):
    """MCP资源定义"""
    uri: str = Field(description="资源URI")
    name: str = Field(description="资源名称")
    description: str = Field(default="", description="资源描述")
    mime_type: str = Field(default="text/plain", description="MIME类型")


class MCPRequest(BaseModel):
    """MCP请求（JSON-RPC 2.0）"""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC版本")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="请求ID")
    method: str = Field(description="方法名")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params
        }


class MCPResponse(BaseModel):
    """MCP响应（JSON-RPC 2.0）"""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC版本")
    id: str = Field(description="请求ID")
    result: Optional[Dict[str, Any]] = Field(default=None, description="成功结果")
    error_info: Optional[Dict[str, Any]] = Field(default=None, alias="error", description="错误信息")

    class Config:
        populate_by_name = True

    def to_dict(self) -> Dict[str, Any]:
        response = {
            "jsonrpc": self.jsonrpc,
            "id": self.id
        }
        if self.result is not None:
            response["result"] = self.result
        if self.error_info is not None:
            response["error"] = self.error_info
        return response

    @classmethod
    def success(cls, request_id: str, result: Dict[str, Any]) -> "MCPResponse":
        """创建成功响应"""
        return cls(id=request_id, result=result)

    @classmethod
    def create_error(
        cls,
        request_id: str,
        code: int,
        message: str,
        data: Any = None
    ) -> "MCPResponse":
        """创建错误响应"""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return cls(id=request_id, error=error)


class MCPError:
    """MCP错误码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # 自定义错误码
    TOOL_NOT_FOUND = -32001
    TOOL_EXECUTION_ERROR = -32002
    RESOURCE_NOT_FOUND = -32003
