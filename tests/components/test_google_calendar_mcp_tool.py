"""
Unit tests for GoogleCalendarMCPTool wrapper.

These tests validate the wrapper layer (tool descriptions, env injection,
missing-token guard) without hitting the real Google Calendar API.
"""

import pytest

from engine.components.tools.google_calendar_mcp_tool import (
    _DEFAULT_TOOLS,
    GoogleCalendarMCPTool,
)
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from tests.mocks.trace_manager import MockTraceManager


async def _make_tool(access_token: str | None = "fake-token") -> GoogleCalendarMCPTool:
    return await GoogleCalendarMCPTool.from_access_token(
        trace_manager=MockTraceManager(project_name="test"),
        component_attributes=ComponentAttributes(component_instance_name="test-gcal"),
        access_token=access_token,
    )


class TestGoogleCalendarMCPToolConstruction:
    @pytest.mark.asyncio
    async def test_from_access_token_sets_env(self):
        tool = await _make_tool("my-token")
        assert tool.env == {"GOOGLE_CALENDAR_ACCESS_TOKEN": "my-token"}

    @pytest.mark.asyncio
    async def test_from_access_token_without_token(self):
        tool = await _make_tool(None)
        assert tool.env is None

    @pytest.mark.asyncio
    async def test_tool_descriptions_match_default_tools(self):
        tool = await _make_tool()
        names = {td.name for td in tool.get_tool_descriptions()}
        assert names == _DEFAULT_TOOLS

    @pytest.mark.asyncio
    async def test_subprocess_args_point_to_server_module(self):
        tool = await _make_tool()
        assert "-m" in tool.args
        assert "engine.components.tools.google_calendar_mcp.server" in tool.args


class TestGoogleCalendarMCPToolRunGuard:
    @pytest.mark.asyncio
    async def test_raises_when_no_token(self):
        tool = await _make_tool(None)
        inputs = MCPToolInputs(tool_name="calendar_list_calendars", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})

    @pytest.mark.asyncio
    async def test_raises_when_empty_token(self):
        tool = await _make_tool("")
        inputs = MCPToolInputs(tool_name="calendar_list_calendars", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})
