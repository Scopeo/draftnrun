from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext

import pytest
import anyio

from engine.agent.tools.mcp_client_tool import MCPClientTool
from engine.agent.types import ComponentAttributes
from mcp import types as mcp_types


class _DummyTraceManager:
    def start_span(self, *_args, **_kwargs):
        return nullcontext()


class _DummySession:
    def __init__(self, _read, _write):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def initialize(self):
        return None

    async def list_tools(self):
        return type("ListToolsResult", (), {"tools": []})()


@pytest.mark.asyncio
async def test_initialize_uses_sse_client_for_http_url(monkeypatch):
    called = {"sse": 0, "stdio": 0}

    @asynccontextmanager
    async def fake_sse_client(*_args, **_kwargs):
        called["sse"] += 1
        yield object(), object()

    @asynccontextmanager
    async def fake_stdio_client(*_args, **_kwargs):
        called["stdio"] += 1
        yield object(), object()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.sse_client", fake_sse_client)
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.stdio_client", fake_stdio_client)
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.ClientSession", _DummySession)

    tool = MCPClientTool(
        trace_manager=_DummyTraceManager(),
        component_attributes=ComponentAttributes(component_instance_name="mcp"),
        server_command="https://example.com/sse",
        server_args='{"timeout": 1, "sse_read_timeout": 2}',
        server_env='{"Authorization": "Bearer token"}',
    )
    await tool.initialize()

    assert called["sse"] == 1
    assert called["stdio"] == 0


@pytest.mark.asyncio
async def test_initialize_uses_streamable_http_for_http_url_without_sse(monkeypatch):
    called = {"sse": 0, "http": 0}

    @asynccontextmanager
    async def fake_sse_client(*_args, **_kwargs):
        called["sse"] += 1
        yield object(), object()

    @asynccontextmanager
    async def fake_streamable_http(*_args, **_kwargs):
        called["http"] += 1
        yield object(), object()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.sse_client", fake_sse_client)
    monkeypatch.setattr(
        "engine.agent.tools.mcp_client_tool.MCPClientTool._streamable_http_client",
        fake_streamable_http,
    )
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.ClientSession", _DummySession)

    tool = MCPClientTool(
        trace_manager=_DummyTraceManager(),
        component_attributes=ComponentAttributes(component_instance_name="mcp"),
        server_command="https://app.mockmcp.com/servers/analv3xwALBr/mcp",
        server_args="{}",
        server_env=None,
    )
    await tool.initialize()

    assert called["sse"] == 0
    assert called["http"] == 1


@pytest.mark.asyncio
async def test_initialize_uses_stdio_client_for_local_command(monkeypatch):
    called = {"sse": 0, "stdio": 0}

    @asynccontextmanager
    async def fake_sse_client(*_args, **_kwargs):
        called["sse"] += 1
        yield object(), object()

    @asynccontextmanager
    async def fake_stdio_client(*_args, **_kwargs):
        called["stdio"] += 1
        yield object(), object()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.sse_client", fake_sse_client)
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.stdio_client", fake_stdio_client)
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.ClientSession", _DummySession)

    tool = MCPClientTool(
        trace_manager=_DummyTraceManager(),
        component_attributes=ComponentAttributes(component_instance_name="mcp"),
        server_command="uvx",
        server_args='["mcp-server-sqlite", "--db-path", "test.db"]',
        server_env='{"API_KEY": "secret"}',
    )
    await tool.initialize()

    assert called["sse"] == 0
    assert called["stdio"] == 1


@pytest.mark.asyncio
async def test_initialize_raises_on_local_command_with_dict_server_args(monkeypatch):
    @asynccontextmanager
    async def fake_stdio_client(*_args, **_kwargs):
        yield object(), object()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.stdio_client", fake_stdio_client)
    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.ClientSession", _DummySession)

    tool = MCPClientTool(
        trace_manager=_DummyTraceManager(),
        component_attributes=ComponentAttributes(component_instance_name="mcp"),
        server_command="uvx",
        server_args='{"timeout": 1}',
        server_env=None,
    )

    with pytest.raises(ValueError, match="server_args"):
        await tool.initialize()


@pytest.mark.asyncio
async def test_run_lazily_initializes_and_supports_list(monkeypatch):
    called = {"sse": 0}

    @asynccontextmanager
    async def fake_sse_client(*_args, **_kwargs):
        called["sse"] += 1
        yield object(), object()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.sse_client", fake_sse_client)

    class _SessionWithTools(_DummySession):
        async def list_tools(self):
            tool_1 = type("Tool", (), {"name": "t1", "description": "", "inputSchema": {}})()
            return type("ListToolsResult", (), {"tools": [tool_1]})()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.ClientSession", _SessionWithTools)

    tool = MCPClientTool(
        trace_manager=_DummyTraceManager(),
        component_attributes=ComponentAttributes(component_instance_name="mcp"),
        server_command="https://example.com/sse",
        server_args="{}",
        server_env=None,
    )

    out = await tool._run_without_io_trace(tool_name="list")
    assert called["sse"] == 1
    assert "t1" in out.messages[0].content


@pytest.mark.asyncio
async def test_streamable_http_does_not_expect_response_for_notification(monkeypatch):
    class _DummyResponse:
        def __init__(self):
            self.headers = {"content-type": "text/plain"}

        def raise_for_status(self):
            return None

        async def aread(self):
            return b""

        async def aiter_lines(self):
            if False:
                yield ""  # pragma: no cover

    class _DummyStreamCtx:
        async def __aenter__(self):
            return _DummyResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _DummyHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *_args, **_kwargs):
            return _DummyStreamCtx()

    monkeypatch.setattr("engine.agent.tools.mcp_client_tool.httpx.AsyncClient", _DummyHttpxClient)

    async with MCPClientTool._streamable_http_client(url="https://example.com/mcp") as (read, write):
        notification = mcp_types.JSONRPCMessage.model_validate({"jsonrpc": "2.0", "method": "initialized"})
        await write.send(notification)
        await write.aclose()

        with pytest.raises(anyio.EndOfStream):
            await read.receive()
