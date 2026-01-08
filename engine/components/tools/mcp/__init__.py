"""MCP (Model Context Protocol) tools for DraftNRun.

This module provides tools for interacting with MCP servers:
- LocalMCPTool: For trusted, hardcoded MCP servers via stdio transport
- RemoteMCPTool: For user-provided MCP servers via HTTP/SSE transport
"""

from .local_mcp_tool import LocalMCPTool
from .remote_mcp_tool import RemoteMCPTool
from .shared import MCPToolInputs, MCPToolOutputs, convert_tool_to_description, process_mcp_result

__all__ = [
    "LocalMCPTool",
    "RemoteMCPTool",
    "MCPToolInputs",
    "MCPToolOutputs",
    "process_mcp_result",
    "convert_tool_to_description",
]
