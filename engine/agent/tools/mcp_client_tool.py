import logging
import json
import os
from typing import Optional, Any, Dict, List
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool as MCPTool

from engine.agent.agent import Agent
from engine.agent.types import (
    AgentPayload,
    ChatMessage,
    ComponentAttributes,
    ToolDescription,
)
from engine.trace.trace_manager import TraceManager
from openinference.semconv.trace import OpenInferenceSpanKindValues
from engine.agent.utils import load_str_to_json

LOGGER = logging.getLogger(__name__)

MCP_CLIENT_TOOL_DESCRIPTION = ToolDescription(
    name="mcp_tools_executor",
    description="Gateway to execute tools on an MCP server. Initialize to see available tools.",
    tool_properties={
        "tool_name": {"type": "string", "description": "The name of the tool to execute."},
        "tool_args": {"type": "object", "description": "The arguments for the tool."},
    },
    required_tool_properties=["tool_name", "tool_args"],
)


class MCPClientTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    
    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        server_command: str,
        server_args: List[str] | str,
        server_env: Optional[Dict[str, str] | str] = None,
        tool_description: Optional[ToolDescription] = MCP_CLIENT_TOOL_DESCRIPTION,
    ):
        if tool_description is None:
             tool_description = MCP_CLIENT_TOOL_DESCRIPTION
            
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.server_command = server_command
        
        # Handle server_args being passed as a string (from DB) or list
        if isinstance(server_args, str):
            try:
                self.server_args = load_str_to_json(server_args)
                if not isinstance(self.server_args, list):
                     # Fallback if JSON parses but isn't a list
                     LOGGER.warning(f"Parsed server_args is not a list: {type(self.server_args)}. Treating as single arg.")
                     self.server_args = [server_args]
            except Exception as e:
                LOGGER.warning(f"Failed to parse server_args string as JSON: {e}. Treating as split string.")
                self.server_args = server_args.split()
        else:
            self.server_args = server_args

        # Handle server_env being passed as a string (from DB) or dict
        if isinstance(server_env, str):
            try:
                self.server_env = load_str_to_json(server_env)
                if not isinstance(self.server_env, dict):
                     LOGGER.warning(f"Parsed server_env is not a dict: {type(self.server_env)}. Ignoring.")
                     self.server_env = None
            except Exception as e:
                LOGGER.error(f"Failed to parse server_env string as JSON: {e}")
                self.server_env = None
        else:
            self.server_env = server_env

        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None
        self._available_tools: List[MCPTool] = []

    async def initialize(self) -> None:
        """
        Connects to the MCP server and fetches available tools.
        Updates the tool_description with the list of available tools.
        """
        server_params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
            env=self.server_env
        )
        
        # Ensure PATH includes common locations to find node, etc.
        current_env = os.environ.copy()
        if self.server_env:
            current_env.update(self.server_env)
        
        # Add common paths to PATH if not already present
        common_paths = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]
        current_path = current_env.get("PATH", "")
        for path in common_paths:
            if path not in current_path.split(os.pathsep):
                current_path = f"{path}{os.pathsep}{current_path}"
        current_env["PATH"] = current_path
        
        server_params.env = current_env
        
        try:
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            read, write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            
            # List tools
            result = await self.session.list_tools()
            self._available_tools = result.tools
            
            # Update description
            tools_details = []
            for t in self._available_tools:
                tools_details.append(f"Tool '{t.name}': {t.description}\nSchema: {json.dumps(t.inputSchema)}")
            
            full_desc = (
                "Gateway to execute tools on the connected MCP server.\n"
                "You must call this tool with 'tool_name' and 'tool_args'.\n"
                "Available tools:\n\n" + "\n\n".join(tools_details)
            )
            
            self.tool_description.description = full_desc
            LOGGER.info(f"Initialized MCP Client with tools: {[t.name for t in self._available_tools]}")
            
        except Exception as e:
            LOGGER.error(f"Failed to initialize MCP client: {e}")
            raise

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        ctx: Optional[dict] = None,
        **kwargs: Any,
    ) -> AgentPayload:
        tool_name = kwargs.get("tool_name")
        tool_args = kwargs.get("tool_args", {})
        
        if isinstance(tool_args, str):
            tool_args = load_str_to_json(tool_args)

        if not self.session:
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content="Error: MCP Client not initialized.")],
                is_final=False,
                error="MCP Client not initialized"
            )

        try:
            result = await self.session.call_tool(tool_name, arguments=tool_args)
            
            # Format output
            content_parts = []
            artifacts = {}
            
            for item in result.content:
                if item.type == "text":
                    content_parts.append(item.text)
                elif item.type == "image":
                    content_parts.append(f"[Image: {item.mimeType}]")
                    # potentially save image to artifacts if needed
            
            content = "\n".join(content_parts)
            
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=content)],
                is_final=False,
                artifacts=artifacts
            )
            
        except Exception as e:
            LOGGER.error(f"Error calling MCP tool {tool_name}: {e}")
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=f"Error calling tool: {e}")],
                is_final=False,
                error=str(e)
            )

    async def close(self):
        await self.exit_stack.aclose()
