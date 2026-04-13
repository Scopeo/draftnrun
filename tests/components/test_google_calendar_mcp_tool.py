"""
Unit tests for GoogleCalendarMCPTool wrapper and server logic.

These tests validate the wrapper layer (tool descriptions, env injection,
missing-token guard) and the MCP tool surface without hitting the real
Google Calendar API.
"""

import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.tools.google_calendar_mcp import server as gcal_server
from engine.components.tools.google_calendar_mcp.client import GoogleCalendarClient
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


class TestGoogleCalendarMCPServerSubprocess:
    def test_server_module_importable_without_backend_env(self):
        """Regression: the stdio subprocess must not transitively import ada_backend,
        which would crash on missing FERNET_KEY / ADA_DB_URL."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import engine.components.tools.google_calendar_mcp.server; "
                    "import sys; "
                    "backend_modules = [m for m in sys.modules if m.startswith('ada_backend')]; "
                    "assert not backend_modules, f'ada_backend leaked into subprocess: {backend_modules}'"
                ),
            ],
            env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Server module failed to import in minimal env:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


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


class TestSendUpdatesParameter:
    """Regression: mutating calls must pass sendUpdates='all' so attendees get email notifications."""

    def _build_mock_service(self):
        service = MagicMock()
        events = MagicMock()
        service.events.return_value = events
        execute = MagicMock(return_value={"id": "evt123", "status": "confirmed"})
        events.insert.return_value.execute = execute
        events.patch.return_value.execute = execute
        events.delete.return_value.execute = MagicMock()
        return service, events

    @pytest.mark.asyncio
    async def test_create_event_sends_updates(self):
        service, events = self._build_mock_service()
        client = object.__new__(GoogleCalendarClient)
        client._service = service
        await client.create_event({"summary": "Test"})
        events.insert.assert_called_once()
        assert events.insert.call_args.kwargs["sendUpdates"] == "all"

    @pytest.mark.asyncio
    async def test_update_event_sends_updates(self):
        service, events = self._build_mock_service()
        client = object.__new__(GoogleCalendarClient)
        client._service = service
        await client.update_event("evt123", {"summary": "Updated"})
        events.patch.assert_called_once()
        assert events.patch.call_args.kwargs["sendUpdates"] == "all"

    @pytest.mark.asyncio
    async def test_delete_event_sends_updates(self):
        service, events = self._build_mock_service()
        client = object.__new__(GoogleCalendarClient)
        client._service = service
        await client.delete_event("evt123")
        events.delete.assert_called_once()
        assert events.delete.call_args.kwargs["sendUpdates"] == "all"


class TestCalendarGetMyEmail:
    @pytest.mark.asyncio
    async def test_returns_user_email(self):
        mock_client = AsyncMock()
        mock_client.get_user_email = AsyncMock(return_value="owner@example.com")
        with patch.object(gcal_server, "_client", mock_client, create=True):
            result = await gcal_server.calendar_get_my_email()
        assert result == {"email": "owner@example.com"}

    @pytest.mark.asyncio
    async def test_get_my_email_in_default_tools(self):
        assert "calendar_get_my_email" in _DEFAULT_TOOLS
