import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from pydantic import SecretStr

from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.tools.outlook_calendar_mcp.client import OutlookCalendarClient
from engine.components.tools.outlook_calendar_mcp_tool import (
    _DEFAULT_TOOLS,
    OutlookCalendarMCPTool,
)
from engine.components.types import ComponentAttributes
from tests.mocks.trace_manager import MockTraceManager


async def _make_tool(access_token: SecretStr | None = SecretStr("fake-token")) -> OutlookCalendarMCPTool:
    return await OutlookCalendarMCPTool.from_access_token(
        trace_manager=MockTraceManager(project_name="test"),
        component_attributes=ComponentAttributes(component_instance_name="test-outlook-cal"),
        access_token=access_token,
    )


class TestOutlookCalendarMCPToolConstruction:
    @pytest.mark.asyncio
    async def test_from_access_token_sets_env(self):
        tool = await _make_tool(SecretStr("my-token"))
        assert tool.env == {"OUTLOOK_CALENDAR_ACCESS_TOKEN": "my-token"}

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
        assert "engine.components.tools.outlook_calendar_mcp.server" in tool.args


class TestOutlookCalendarMCPServerSubprocess:
    def test_server_module_importable_without_backend_env(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import engine.components.tools.outlook_calendar_mcp.server; "
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


class TestOutlookCalendarClientUrlEncoding:
    RAW_CAL_ID = "AAMkAGI2+Strange/Id="
    RAW_EVENT_ID = "EV+test/foo="
    ENCODED_CAL_ID = quote(RAW_CAL_ID, safe="")
    ENCODED_EVENT_ID = quote(RAW_EVENT_ID, safe="")

    @staticmethod
    def _fake_response(data: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = data or {}
        return resp

    def _make_client(self) -> OutlookCalendarClient:
        client = OutlookCalendarClient(access_token="fake")
        client._default_calendar_id = self.RAW_CAL_ID
        return client

    @pytest.mark.asyncio
    async def test_list_events_encodes_calendar_id(self):
        client = self._make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = self._fake_response({"value": []})
            await client.list_events(calendar_id="primary")
            path = mock_req.call_args[0][1]
            assert self.ENCODED_CAL_ID in path
            assert self.RAW_CAL_ID not in path

    @pytest.mark.asyncio
    async def test_get_event_encodes_event_id(self):
        client = self._make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = self._fake_response()
            await client.get_event(self.RAW_EVENT_ID)
            path = mock_req.call_args[0][1]
            assert self.ENCODED_EVENT_ID in path
            assert self.RAW_EVENT_ID not in path

    @pytest.mark.asyncio
    async def test_create_event_encodes_calendar_id(self):
        client = self._make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = self._fake_response()
            await client.create_event({"subject": "test"}, calendar_id="primary")
            path = mock_req.call_args[0][1]
            assert self.ENCODED_CAL_ID in path
            assert self.RAW_CAL_ID not in path

    @pytest.mark.asyncio
    async def test_update_event_encodes_event_id(self):
        client = self._make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = self._fake_response()
            await client.update_event(self.RAW_EVENT_ID, {"subject": "updated"})
            path = mock_req.call_args[0][1]
            assert self.ENCODED_EVENT_ID in path
            assert self.RAW_EVENT_ID not in path

    @pytest.mark.asyncio
    async def test_delete_event_encodes_event_id(self):
        client = self._make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.delete_event(self.RAW_EVENT_ID)
            path = mock_req.call_args[0][1]
            assert self.ENCODED_EVENT_ID in path
            assert self.RAW_EVENT_ID not in path


class TestOutlookCalendarMCPToolRunGuard:
    @pytest.mark.asyncio
    async def test_raises_when_no_token(self):
        tool = await _make_tool(None)
        inputs = MCPToolInputs(tool_name="outlook_calendar_list_calendars", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})

    @pytest.mark.asyncio
    async def test_raises_when_empty_token(self):
        tool = await _make_tool(SecretStr(""))
        inputs = MCPToolInputs(tool_name="outlook_calendar_list_calendars", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})
