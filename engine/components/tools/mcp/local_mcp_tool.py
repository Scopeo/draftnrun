import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, Self

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from openinference.semconv.trace import OpenInferenceSpanKindValues

from engine.components.component import Component
from engine.components.errors import MCPConnectionError
from engine.components.tools.mcp.shared import (
    DEFAULT_MCP_TOOL_DESCRIPTION,
    MCPToolInputs,
    MCPToolOutputs,
    convert_tool_to_description,
    execute_mcp_tool_call,
)
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class LocalMCPTool(Component):
    """
    Expose tools from a local MCP server (stdio transport) as individual tool calls.

    Maintains a persistent subprocess and session for the lifetime of this instance,
    so state is shared across multiple tool calls.

    WARNING: This component spawns subprocess with arbitrary commands.
    NEVER expose this to frontend or allow user-provided commands.
    Only use with hardcoded, trusted commands.
    """

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True
    requires_tool_name = True

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: int = 30,
        tool_descriptions: list[ToolDescription] | None = None,
    ):
        """
        Initialize LocalMCPTool.

        Args:
            command: Command to execute (e.g., "python", "node", "uv")
            args: Command arguments (e.g., ["-m", "fastmcp", "run", "server.py"])
            env: Optional environment variables
            cwd: Optional working directory
            timeout: Timeout in seconds
            tool_descriptions: Tool descriptions (required, or use from_mcp_server)
        """
        if not command:
            raise ValueError("command is required for LocalMCPTool.")

        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = Path(cwd) if cwd else None
        self.timeout = timeout

        if tool_descriptions is None:
            raise ValueError("Provide tool_descriptions or use LocalMCPTool.from_mcp_server for auto-discovery.")

        self._mcp_tool_descriptions = tool_descriptions
        self._tool_description_map = {td.name: td for td in self._mcp_tool_descriptions}

        # Persistent session management
        self._session: Optional[ClientSession] = None
        self._stdio_context = None
        self._session_exit_stack = None

        super().__init__(
            trace_manager=trace_manager,
            tool_description=(
                self._mcp_tool_descriptions[0] if self._mcp_tool_descriptions else DEFAULT_MCP_TOOL_DESCRIPTION
            ),
            component_attributes=component_attributes,
        )

    def get_tool_descriptions(self) -> list[ToolDescription]:
        """Return all tool descriptions fetched from the MCP server."""
        return self._mcp_tool_descriptions

    def _get_server_params(self) -> StdioServerParameters:
        """Build StdioServerParameters from config."""
        return StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
            cwd=self.cwd,
        )

    async def _ensure_session(self):
        """Ensure the MCP session is initialized. Creates it if it doesn't exist."""
        if self._session is not None:
            return

        server_params = self._get_server_params()
        try:
            # Store the context managers to keep the session alive
            self._stdio_context = stdio_client(server_params)
            read, write = await self._stdio_context.__aenter__()

            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()

            LOGGER.info(f"Initialized persistent MCP session for {self.command}")
        except Exception as exc:
            error_label = f"stdio://{self.command} {' '.join(self.args)}"
            raise MCPConnectionError(error_label, str(exc)) from exc

    async def close(self):
        """Close the persistent MCP session and cleanup subprocess."""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                LOGGER.warning(f"Error closing MCP session: {e}")
            finally:
                self._session = None

        if self._stdio_context is not None:
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except Exception as e:
                LOGGER.warning(f"Error closing stdio context: {e}")
            finally:
                self._stdio_context = None

        LOGGER.info(f"Closed persistent MCP session for {self.command}")

    async def __aenter__(self):
        """Support async context manager."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support async context manager."""
        await self.close()
        return False

    @classmethod
    async def from_mcp_server(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: int = 30,
    ) -> Self:
        """
        Convenience async constructor that fetches tool descriptions via MCP SDK.

        Creates a single persistent subprocess/session and uses it for both tool
        discovery and subsequent operations.

        Example:
            tool = await LocalMCPTool.from_mcp_server(
                trace_manager=tm,
                component_attributes=attrs,
                command="uv",
                args=["run", "python", "scripts/fastmcp_debug_server.py"],
            )
        """
        if not command:
            raise ValueError("command is required for LocalMCPTool.")

        instance = cls.__new__(cls)
        instance.command = command
        instance.args = args or []
        instance.env = env
        instance.cwd = Path(cwd) if cwd else None
        instance.timeout = timeout
        instance._session = None
        instance._stdio_context = None

        try:
            await instance._ensure_session()
        except Exception as exc:
            error_label = f"stdio://{command} {' '.join(instance.args)}"
            raise MCPConnectionError(error_label, str(exc)) from exc

        assert instance._session is not None
        try:
            tools_result = await instance._session.list_tools()
        except Exception as exc:
            await instance.close()
            error_label = f"stdio://{command} {' '.join(instance.args)}"
            raise MCPConnectionError(error_label, str(exc)) from exc

        tools = list(getattr(tools_result, "tools", []) or [])

        tool_descriptions: list[ToolDescription] = []
        for tool in tools:
            description = convert_tool_to_description(tool)
            if description:
                tool_descriptions.append(description)

        instance._mcp_tool_descriptions = tool_descriptions
        instance._tool_description_map = {td.name: td for td in tool_descriptions}
        super(LocalMCPTool, instance).__init__(
            trace_manager=trace_manager,
            tool_description=(
                instance._mcp_tool_descriptions[0] if instance._mcp_tool_descriptions else DEFAULT_MCP_TOOL_DESCRIPTION
            ),
            component_attributes=component_attributes,
        )

        return instance

    @classmethod
    def get_inputs_schema(cls):
        return MCPToolInputs

    @classmethod
    def get_outputs_schema(cls):
        return MCPToolOutputs

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        return await execute_mcp_tool_call(
            inputs=inputs,
            tool_description_map=self._tool_description_map,
            call_tool_fn=self._call_tool_with_sdk,
            tool_type_name="local",
            trace_span_kind=self.TRACE_SPAN_KIND,
        )

    async def _call_tool_with_sdk(self, tool_name: str, arguments: dict[str, Any]):
        """Use MCP SDK to call a tool via persistent stdio session."""
        await self._ensure_session()

        try:
            return await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments=arguments),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as exc:
            error_label = f"stdio://{self.command} {' '.join(self.args)}"
            raise MCPConnectionError(error_label, f"Tool call timed out after {self.timeout}s") from exc
        except Exception as exc:
            error_label = f"stdio://{self.command} {' '.join(self.args)}"
            raise MCPConnectionError(error_label, str(exc)) from exc
