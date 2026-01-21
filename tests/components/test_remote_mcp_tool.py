import asyncio
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.errors import MCPConnectionError
from engine.components.tools.mcp.remote_mcp_tool import RemoteMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def component_attributes():
    return ComponentAttributes(component_instance_name="remote-mcp-test")


def create_mock_tool(
    name: str,
    description: str,
    properties: dict | None = None,
    required: list | None = None,
):
    """Helper to create a mock MCP tool."""
    mock_tool = MagicMock()
    mock_tool.name = name
    mock_tool.description = description
    mock_tool.inputSchema = {
        "properties": properties or {},
        "required": required or [],
    }
    return mock_tool


def create_mock_list_result(tools: list):
    """Helper to create a mock list_tools result."""
    mock_result = MagicMock()
    mock_result.tools = tools
    return mock_result


def create_mock_call_result(text_content: str = None, is_error: bool = False):
    """Helper to create a mock call_tool result."""
    mock_result = MagicMock()
    if text_content:
        mock_item = MagicMock()
        mock_item.text = text_content
        mock_result.content = [mock_item]
    else:
        mock_result.content = []
    mock_result.isError = is_error
    return mock_result


@contextmanager
def mock_mcp_sdk(list_tools_result=None, call_tool_result=None):
    """Context manager to mock the MCP SDK (sse_client and ClientSession)."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()

    if list_tools_result is not None:
        mock_session.list_tools = AsyncMock(return_value=list_tools_result)
    if call_tool_result is not None:
        mock_session.call_tool = AsyncMock(return_value=call_tool_result)

    mock_read = MagicMock()
    mock_write = MagicMock()

    mock_sse_ctx = AsyncMock()
    mock_sse_ctx.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
    mock_sse_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    def mock_sse_client(server_url, headers=None, timeout=None):
        return mock_sse_ctx

    def mock_client_session(read, write):
        return mock_session_ctx

    with (
        patch("engine.components.tools.mcp.remote_mcp_tool.sse_client", mock_sse_client),
        patch("engine.components.tools.mcp.remote_mcp_tool.ClientSession", mock_client_session),
    ):
        yield mock_session


def test_from_mcp_server_fetches_and_converts_tools(mock_trace_manager, component_attributes):
    """Test that from_mcp_server correctly fetches tools and converts them to ToolDescriptions."""
    mock_tool1 = create_mock_tool("get_weather", "Get weather for a city", {"city": {"type": "string"}}, ["city"])
    mock_tool2 = create_mock_tool("list_users", "List users", {}, [])
    mock_tool3 = create_mock_tool(
        "create_task",
        "Create a task",
        {"title": {"type": "string"}, "priority": {"type": "integer"}},
        ["title"],
    )

    mock_list_result = create_mock_list_result([mock_tool1, mock_tool2, mock_tool3])

    async def run_test():
        with mock_mcp_sdk(list_tools_result=mock_list_result) as mock_session:
            mcp_tool = await RemoteMCPTool.from_mcp_server(
                trace_manager=mock_trace_manager,
                component_attributes=component_attributes,
                server_url="https://mcp.example.com",
                headers={"Authorization": "Bearer token123"},
                timeout=60,
            )

            # Verify tool descriptions were created correctly
            descriptions = mcp_tool.get_tool_descriptions()
            assert len(descriptions) == 3

            assert descriptions[0].name == "get_weather"
            assert descriptions[0].description == "Get weather for a city"
            assert descriptions[0].tool_properties == {"city": {"type": "string"}}
            assert descriptions[0].required_tool_properties == ["city"]

            assert descriptions[1].name == "list_users"
            assert descriptions[1].description == "List users"
            assert descriptions[1].tool_properties == {}
            assert descriptions[1].required_tool_properties == []

            assert descriptions[2].name == "create_task"
            assert descriptions[2].tool_properties == {
                "title": {"type": "string"},
                "priority": {"type": "integer"},
            }
            assert descriptions[2].required_tool_properties == ["title"]

            # Verify default tool_description is set to first tool
            assert mcp_tool.tool_description.name == "get_weather"

            # Verify SDK was called correctly
            mock_session.initialize.assert_called_once()
            mock_session.list_tools.assert_called_once()

    asyncio.run(run_test())


def test_from_mcp_server_handles_empty_tools_list(mock_trace_manager, component_attributes):
    """Test that from_mcp_server handles empty tools list gracefully."""
    mock_list_result = create_mock_list_result([])

    async def run_test():
        with mock_mcp_sdk(list_tools_result=mock_list_result):
            mcp_tool = await RemoteMCPTool.from_mcp_server(
                trace_manager=mock_trace_manager,
                component_attributes=component_attributes,
                server_url="https://mcp.example.com",
            )

            descriptions = mcp_tool.get_tool_descriptions()
            assert len(descriptions) == 0

    asyncio.run(run_test())


def test_from_mcp_server_skips_tools_without_name(mock_trace_manager, component_attributes):
    """Test that tools without a name are skipped."""
    mock_tool1 = create_mock_tool("valid_tool", "Valid tool")
    mock_tool2 = MagicMock()  # Tool without name
    mock_tool2.name = None
    mock_tool2.description = "Invalid tool"
    mock_tool2.inputSchema = {}

    mock_list_result = create_mock_list_result([mock_tool1, mock_tool2])

    async def run_test():
        with mock_mcp_sdk(list_tools_result=mock_list_result):
            mcp_tool = await RemoteMCPTool.from_mcp_server(
                trace_manager=mock_trace_manager,
                component_attributes=component_attributes,
                server_url="https://mcp.example.com",
            )

            descriptions = mcp_tool.get_tool_descriptions()
            assert len(descriptions) == 1
            assert descriptions[0].name == "valid_tool"

    asyncio.run(run_test())


def test_run_executes_tool_successfully(mock_trace_manager, component_attributes):
    """Test that run correctly executes a tool and processes the response."""
    tool_descriptions = [
        ToolDescription(
            name="list_issues",
            description="List issues",
            tool_properties={
                "first": {"type": "integer"},
                "filter": {"type": "string"},
            },
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        headers={"Authorization": "Bearer token"},
        tool_descriptions=tool_descriptions,
    )

    mock_call_result = create_mock_call_result(json.dumps([{"id": "1", "title": "Issue 1"}]), is_error=False)

    async def run_test():
        with mock_mcp_sdk(call_tool_result=mock_call_result) as mock_session:
            result = await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="list_issues", tool_arguments={"first": 10}),
                ctx={},
            )

            # Verify result
            assert isinstance(result, MCPToolOutputs)
            assert json.loads(result.output) == [{"id": "1", "title": "Issue 1"}]
            assert result.is_error is False
            assert len(result.content) == 1

            # Verify SDK was called correctly
            mock_session.initialize.assert_called_once()
            mock_session.call_tool.assert_called_once_with("list_issues", arguments={"first": 10})

    asyncio.run(run_test())


def test_run_handles_multiple_content_items(mock_trace_manager, component_attributes):
    """Test that run correctly handles multiple content items in the response."""
    tool_descriptions = [
        ToolDescription(
            name="get_data",
            description="Get data",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    # Create result with multiple content items
    mock_result = MagicMock()
    item1 = MagicMock()
    item1.text = "First part"
    item2 = MagicMock()
    item2.text = "Second part"
    mock_result.content = [item1, item2]
    mock_result.isError = False

    async def run_test():
        with mock_mcp_sdk(call_tool_result=mock_result):
            result = await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="get_data", tool_arguments={}),
                ctx={},
            )

            # Verify content is concatenated
            assert result.output == "First part\nSecond part"
            assert len(result.content) == 2

    asyncio.run(run_test())


def test_run_handles_empty_content(mock_trace_manager, component_attributes):
    """Test that run handles empty content gracefully."""
    tool_descriptions = [
        ToolDescription(
            name="empty_tool",
            description="Returns empty",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    mock_result = create_mock_call_result(text_content=None, is_error=False)

    async def run_test():
        with mock_mcp_sdk(call_tool_result=mock_result):
            result = await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="empty_tool", tool_arguments={}),
                ctx={},
            )

            # Should return default success message
            assert result.output == json.dumps({"result": "success"})

    asyncio.run(run_test())


def test_run_handles_error_response(mock_trace_manager, component_attributes):
    """Test that run correctly handles error responses."""
    tool_descriptions = [
        ToolDescription(
            name="failing_tool",
            description="Fails",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    mock_result = create_mock_call_result(text_content="Error occurred", is_error=True)

    async def run_test():
        with mock_mcp_sdk(call_tool_result=mock_result):
            result = await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="failing_tool", tool_arguments={}),
                ctx={},
            )

            assert result.output == "Error occurred"
            assert result.is_error is True

    asyncio.run(run_test())


def test_run_validates_tool_name_required(mock_trace_manager, component_attributes):
    """Test that run raises error when tool_name is missing."""
    tool_descriptions = [
        ToolDescription(
            name="some_tool",
            description="Some tool",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    async def run_test():
        with pytest.raises(ValueError, match="tool_name is required"):
            await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="", tool_arguments={}),
                ctx={},
            )

    asyncio.run(run_test())


def test_run_validates_tool_exists(mock_trace_manager, component_attributes):
    """Test that run raises error when tool doesn't exist in registry."""
    tool_descriptions = [
        ToolDescription(
            name="existing_tool",
            description="Existing tool",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    async def run_test():
        with pytest.raises(ValueError, match="Tool nonexistent_tool not found in MCP registry"):
            await mcp_tool._run_without_io_trace(
                inputs=MCPToolInputs(tool_name="nonexistent_tool", tool_arguments={}),
                ctx={},
            )

    asyncio.run(run_test())


def test_init_requires_tool_descriptions(mock_trace_manager, component_attributes):
    """Test that __init__ raises error when tool_descriptions is not provided."""
    with pytest.raises(
        ValueError,
        match="Provide tool_descriptions or use RemoteMCPTool.from_mcp_server",
    ):
        RemoteMCPTool(
            trace_manager=mock_trace_manager,
            component_attributes=component_attributes,
            server_url="https://mcp.example.com",
            tool_descriptions=None,
        )


def test_init_handles_string_headers(mock_trace_manager, component_attributes):
    """Test that __init__ correctly parses string headers."""
    tool_descriptions = [
        ToolDescription(
            name="test_tool",
            description="Test",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    headers_json = '{"Authorization": "Bearer token123", "X-Custom": "value"}'

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        headers=headers_json,
        tool_descriptions=tool_descriptions,
    )

    assert mcp_tool.headers == {"Authorization": "Bearer token123", "X-Custom": "value"}


def test_init_strips_trailing_slash_from_url(mock_trace_manager, component_attributes):
    """Test that __init__ strips trailing slash from server_url."""
    tool_descriptions = [
        ToolDescription(
            name="test_tool",
            description="Test",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com/",
        tool_descriptions=tool_descriptions,
    )

    assert mcp_tool.server_url == "https://mcp.example.com"


def test_from_mcp_server_wraps_connection_errors(mock_trace_manager, component_attributes):
    """Test that connection errors are wrapped with a friendly message."""

    async def run_test():
        with patch.object(RemoteMCPTool, "_list_tools_with_sdk", side_effect=RuntimeError("boom")):
            with pytest.raises(
                MCPConnectionError, match="MCP Tool failed to connect to https://mcp.example.com: boom"
            ):
                await RemoteMCPTool.from_mcp_server(
                    trace_manager=mock_trace_manager,
                    component_attributes=component_attributes,
                    server_url="https://mcp.example.com",
                )

    asyncio.run(run_test())


def test_call_tool_wraps_connection_errors(mock_trace_manager, component_attributes):
    """Test that call_tool connection errors are wrapped with a friendly message."""
    tool_descriptions = [
        ToolDescription(
            name="tool1",
            description="Tool 1",
            tool_properties={},
            required_tool_properties=[],
        )
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    async def run_test():
        with patch("engine.components.tools.mcp.remote_mcp_tool.sse_client", side_effect=RuntimeError("network down")):
            with pytest.raises(
                MCPConnectionError,
                match="MCP Tool failed to connect to https://mcp.example.com: network down",
            ):
                await mcp_tool._run_without_io_trace(
                    inputs=MCPToolInputs(tool_name="tool1", tool_arguments={}),
                    ctx={},
                )

    asyncio.run(run_test())


def test_get_tool_descriptions_returns_all_tools(mock_trace_manager, component_attributes):
    """Test that get_tool_descriptions returns all tool descriptions."""
    tool_descriptions = [
        ToolDescription(
            name="tool1",
            description="Tool 1",
            tool_properties={},
            required_tool_properties=[],
        ),
        ToolDescription(
            name="tool2",
            description="Tool 2",
            tool_properties={},
            required_tool_properties=[],
        ),
        ToolDescription(
            name="tool3",
            description="Tool 3",
            tool_properties={},
            required_tool_properties=[],
        ),
    ]

    mcp_tool = RemoteMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        server_url="https://mcp.example.com",
        tool_descriptions=tool_descriptions,
    )

    descriptions = mcp_tool.get_tool_descriptions()
    assert len(descriptions) == 3
    assert all(desc in descriptions for desc in tool_descriptions)
