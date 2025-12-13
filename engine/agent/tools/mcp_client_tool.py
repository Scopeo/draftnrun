import logging
import json
import os
from typing import Optional, Any, Dict, List
from contextlib import AsyncExitStack, asynccontextmanager
from urllib.parse import urlparse
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp import types as mcp_types
from mcp.types import Tool as MCPTool
from opentelemetry.trace import get_current_span
from openinference.semconv.trace import SpanAttributes
import httpx
import anyio

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
from engine.trace.serializer import serialize_to_json

LOGGER = logging.getLogger(__name__)

MCP_CLIENT_TOOL_DESCRIPTION = ToolDescription(
    name="mcp_tools_executor",
    description="Gateway to execute tools on an MCP server. Initialize to see available tools.",
    tool_properties={
        "tool_name": {"type": "string", "description": "The name of the tool to execute."},
        "tool_args": {"type": "object", "description": "The arguments for the tool."},
    },
    required_tool_properties=["tool_name"],
)


class MCPClientTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _should_use_sse_transport(url: str, server_args: Any) -> bool:
        # Heuristic: if the user explicitly set transport=sse or the URL looks like an SSE endpoint.
        parsed = urlparse(url)
        if parsed.path.endswith("/sse"):
            return True
        if isinstance(server_args, dict):
            transport = server_args.get("transport") or server_args.get("transport_type")
            return transport == "sse"
        return False

    @staticmethod
    def _summarize_exception_group(exc: ExceptionGroup) -> str:
        messages: list[str] = []
        for inner in exc.exceptions:
            messages.append(f"{type(inner).__name__}: {inner}")
        return "; ".join(messages) if messages else str(exc)

    @staticmethod
    @asynccontextmanager
    async def _streamable_http_client(
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: float = 30.0,
        stream_read_timeout: float = 60.0 * 5,
    ):
        """
        Streamable HTTP transport.

        Unlike SSE, the server is contacted via HTTP POST requests (no long-lived GET).
        This transport pushes each response JSON-RPC message back into the read stream.
        """
        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        httpx_timeout = httpx.Timeout(timeout, read=stream_read_timeout)
        async with httpx.AsyncClient(headers=headers, timeout=httpx_timeout) as client:
            writer_task: Optional[asyncio.Task] = None

            async def post_writer():
                try:
                    async with write_stream_reader:
                        async for message in write_stream_reader:
                            payload = message.model_dump(by_alias=True, mode="json", exclude_none=True)
                            expect_response = not isinstance(message.root, mcp_types.JSONRPCNotification)
                            async with client.stream("POST", url, json=payload) as response:
                                response.raise_for_status()
                                content_type = response.headers.get("content-type", "")

                                if not expect_response:
                                    # JSON-RPC notifications don't have a response by design.
                                    # Some servers return 202 Accepted with an empty body for notifications.
                                    await response.aread()
                                    continue

                                if "application/json" in content_type:
                                    body = await response.aread()
                                    parsed = json.loads(body.decode("utf-8"))
                                    if isinstance(parsed, list):
                                        for item in parsed:
                                            await read_stream_writer.send(
                                                mcp_types.JSONRPCMessage.model_validate(item)
                                            )
                                    else:
                                        await read_stream_writer.send(mcp_types.JSONRPCMessage.model_validate(parsed))
                                    continue

                                # Streamable responses (JSONL / SSE-like "data:" lines)
                                sent_any = False
                                async for line in response.aiter_lines():
                                    line = (line or "").strip()
                                    if not line:
                                        continue
                                    if line.startswith("data:"):
                                        line = line[len("data:") :].strip()
                                    try:
                                        parsed = json.loads(line)
                                    except ValueError:
                                        continue
                                    await read_stream_writer.send(mcp_types.JSONRPCMessage.model_validate(parsed))
                                    sent_any = True

                                if not sent_any:
                                    raise ValueError(
                                        "Streamable HTTP response did not contain a JSON-RPC message. "
                                        f"content-type={content_type}"
                                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await read_stream_writer.send(exc)
                finally:
                    await read_stream_writer.aclose()

            writer_task = asyncio.create_task(post_writer())
            try:
                yield read_stream, write_stream
            finally:
                if writer_task is not None and not writer_task.done():
                    writer_task.cancel()
                    try:
                        await writer_task
                    except asyncio.CancelledError:
                        pass
                await write_stream.aclose()
                await write_stream_reader.aclose()

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        server_command: str,
        server_args: List[str] | Dict[str, Any] | str,
        server_env: Optional[Dict[str, Any] | str] = None,
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
            server_args_str = server_args.strip()
            if server_args_str.startswith("[") or server_args_str.startswith("{"):
                try:
                    self.server_args = load_str_to_json(server_args)
                except ValueError as e:
                    LOGGER.warning(
                        f"Failed to parse server_args string as JSON ({type(e).__name__}: {e}). "
                        "Treating as split string."
                    )
                    self.server_args = server_args.split()
            else:
                self.server_args = server_args.split()
        else:
            self.server_args = server_args

        # Handle server_env being passed as a string (from DB) or dict
        if isinstance(server_env, str):
            server_env_str = server_env.strip()
            if server_env_str.startswith("{"):
                try:
                    self.server_env = load_str_to_json(server_env)
                    if not isinstance(self.server_env, dict):
                        LOGGER.warning(f"Parsed server_env is not a dict: {type(self.server_env)}. Ignoring.")
                        self.server_env = None
                except ValueError as e:
                    LOGGER.error(f"Failed to parse server_env string as JSON ({type(e).__name__}: {e})")
                    self.server_env = None
            else:
                LOGGER.warning("server_env was provided but is not a JSON object string. Ignoring.")
                self.server_env = None
        else:
            self.server_env = server_env

        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None
        self._available_tools: List[MCPTool] = []
        self._init_lock = asyncio.Lock()
        self._initialization_error: Optional[str] = None

    async def initialize(self) -> None:
        """
        Connects to the MCP server and fetches available tools.
        Updates the tool_description with the list of available tools.
        """
        try:
            if self._is_http_url(self.server_command):
                headers: Optional[dict[str, Any]] = None
                timeout = 5.0
                sse_read_timeout = 60.0 * 5

                if isinstance(self.server_env, dict):
                    headers = self.server_env

                if isinstance(self.server_args, dict):
                    args_headers = self.server_args.get("headers")
                    if isinstance(args_headers, dict):
                        headers = {**(headers or {}), **args_headers}
                    timeout = float(self.server_args.get("timeout", timeout))
                    sse_read_timeout = float(self.server_args.get("sse_read_timeout", sse_read_timeout))

                if self._should_use_sse_transport(self.server_command, self.server_args):
                    sse_transport = await self.exit_stack.enter_async_context(
                        sse_client(
                            url=self.server_command,
                            headers=headers,
                            timeout=timeout,
                            sse_read_timeout=sse_read_timeout,
                        )
                    )
                    read, write = sse_transport
                else:
                    stream_read_timeout = sse_read_timeout
                    if isinstance(self.server_args, dict):
                        stream_read_timeout = float(
                            self.server_args.get(
                                "stream_read_timeout",
                                self.server_args.get("sse_read_timeout", sse_read_timeout),
                            )
                        )
                    http_transport = await self.exit_stack.enter_async_context(
                        self._streamable_http_client(
                            url=self.server_command,
                            headers=headers,
                            timeout=timeout,
                            stream_read_timeout=stream_read_timeout,
                        )
                    )
                    read, write = http_transport
            else:
                if not isinstance(self.server_args, list):
                    raise ValueError(
                        "Invalid MCP local configuration: 'server_args' must be a JSON list when 'server_command' "
                        "is a local command."
                    )
                server_params = StdioServerParameters(
                    command=self.server_command,
                    args=self.server_args,
                    env=self.server_env if isinstance(self.server_env, dict) else None,
                )

                # Ensure PATH includes common locations to find node, etc.
                current_env = os.environ.copy()
                if isinstance(self.server_env, dict):
                    current_env.update(self.server_env)

                # Add common paths to PATH if not already present
                common_paths = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]
                current_path = current_env.get("PATH", "")
                for path in common_paths:
                    if path not in current_path.split(os.pathsep):
                        current_path = f"{path}{os.pathsep}{current_path}"
                current_env["PATH"] = current_path

                server_params.env = current_env

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

        except ExceptionGroup as e:
            summarized = self._summarize_exception_group(e)
            self._initialization_error = summarized
            LOGGER.error(f"Failed to initialize MCP client (ExceptionGroup): {summarized}")
            raise ValueError(
                "Failed to initialize MCP client due to grouped async errors. "
                f"Details: {summarized}. If you're connecting remotely, make sure 'server_command' matches the "
                "server transport: SSE endpoints often end with '/sse', while streamable-http endpoints often end "
                "with '/mcp'."
            ) from e
        except (OSError, ValueError, httpx.HTTPError) as e:
            self._initialization_error = f"{type(e).__name__}: {e}"
            LOGGER.error(f"Failed to initialize MCP client ({type(e).__name__}): {e}")
            raise

    async def _ensure_initialized(self) -> None:
        if self.session is not None:
            return
        async with self._init_lock:
            if self.session is not None:
                return
            await self.initialize()

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        ctx: Optional[dict] = None,
        **kwargs: Any,
    ) -> AgentPayload:
        tool_name = kwargs.get("tool_name")
        tool_args = kwargs.get("tool_args", {})

        agent_input = inputs[0] if inputs else None
        if agent_input is not None:
            agent_input_dict = agent_input.model_dump(exclude_none=True, exclude_unset=True)
            if tool_name is None:
                tool_name = agent_input_dict.get("tool_name")
            if tool_args == {}:
                tool_args = agent_input_dict.get("tool_args", {})

        if isinstance(tool_args, str):
            tool_args = load_str_to_json(tool_args)

        span = get_current_span()
        trace_input = serialize_to_json(
            {"tool_name": tool_name, "tool_args": tool_args},
            shorten_string=True,
        )
        span.set_attributes(
            {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
                SpanAttributes.TOOL_PARAMETERS: trace_input,
            }
        )

        if not self.session:
            if self._initialization_error:
                return AgentPayload(
                    messages=[
                        ChatMessage(
                            role="assistant",
                            content=f"Error: MCP Client failed to initialize. Details: {self._initialization_error}",
                        )
                    ],
                    is_final=False,
                    error=f"MCP Client failed to initialize: {self._initialization_error}",
                )
            try:
                await self._ensure_initialized()
            except (OSError, ValueError, httpx.HTTPError, ExceptionGroup) as e:
                return AgentPayload(
                    messages=[
                        ChatMessage(
                            role="assistant",
                            content=f"Error: MCP Client failed to initialize ({type(e).__name__}): {e}",
                        )
                    ],
                    is_final=False,
                    error=str(e),
                )

        if tool_name in {"initialize", "init"}:
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content="MCP Client initialized.")],
                is_final=False,
            )

        if tool_name in {"list", "list_tools"}:
            tool_names = [t.name for t in self._available_tools]
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=json.dumps({"tools": tool_names}))],
                is_final=False,
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
                messages=[ChatMessage(role="assistant", content=content)], is_final=False, artifacts=artifacts
            )

        except Exception as e:
            LOGGER.error(f"Error calling MCP tool {tool_name} ({type(e).__name__}): {e}")
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=f"Error calling tool ({type(e).__name__}): {e}")],
                is_final=False,
                error=str(e),
            )

    async def close(self):
        await self.exit_stack.aclose()
