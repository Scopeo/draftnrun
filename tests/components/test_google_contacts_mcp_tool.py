"""
Unit tests for GoogleContactsMCPTool wrapper and server logic.

These tests validate the wrapper layer and read-only People API client behavior
without hitting the real Google Contacts API.
"""

import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from engine.components.tools.google_contacts_mcp import server as contacts_server
from engine.components.tools.google_contacts_mcp.client import (
    DEFAULT_OTHER_CONTACTS_READ_MASK,
    DEFAULT_PERSON_FIELDS,
    GoogleContactsClient,
)
from engine.components.tools.google_contacts_mcp_tool import (
    _DEFAULT_TOOLS,
    GoogleContactsMCPTool,
)
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from tests.mocks.trace_manager import MockTraceManager


async def _make_tool(access_token: SecretStr | None = SecretStr("fake-token")) -> GoogleContactsMCPTool:
    return await GoogleContactsMCPTool.from_access_token(
        trace_manager=MockTraceManager(project_name="test"),
        component_attributes=ComponentAttributes(component_instance_name="test-contacts"),
        access_token=access_token,
    )


class TestGoogleContactsMCPToolConstruction:
    @pytest.mark.asyncio
    async def test_from_access_token_sets_env(self):
        tool = await _make_tool(SecretStr("my-token"))
        assert tool.env == {"GOOGLE_CONTACTS_ACCESS_TOKEN": "my-token"}

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
        assert "engine.components.tools.google_contacts_mcp.server" in tool.args


class TestGoogleContactsMCPServerSubprocess:
    def test_server_module_importable_without_backend_env(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import engine.components.tools.google_contacts_mcp.server; "
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


class TestGoogleContactsMCPToolRunGuard:
    @pytest.mark.asyncio
    async def test_raises_when_no_token(self):
        tool = await _make_tool(None)
        inputs = MCPToolInputs(tool_name="contacts_list_contacts", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})

    @pytest.mark.asyncio
    async def test_raises_when_empty_token(self):
        tool = await _make_tool(SecretStr(""))
        inputs = MCPToolInputs(tool_name="contacts_list_contacts", tool_arguments={})
        with pytest.raises(ValueError, match="OAuth connection"):
            await tool._run_without_io_trace(inputs, ctx={})


class TestGoogleContactsClient:
    @pytest.mark.asyncio
    async def test_list_contacts_returns_normalized_payload(self):
        service = MagicMock()
        people = service.people.return_value
        connections = people.connections.return_value
        connections.list.return_value.execute.return_value = {
            "connections": [{"resourceName": "people/c123"}],
            "nextPageToken": "next-page",
            "totalPeople": 1,
        }
        service.otherContacts.return_value.list.return_value.execute.return_value = {
            "otherContacts": [{"resourceName": "otherContacts/c456"}],
            "nextPageToken": "next-other-page",
            "totalSize": 1,
        }

        client = object.__new__(GoogleContactsClient)
        client._build_service = MagicMock(return_value=service)

        result = await client.list_contacts(
            max_results=25,
            person_fields=DEFAULT_PERSON_FIELDS,
            other_contacts_page_token="other-page",
        )

        connections.list.assert_called_once_with(
            resourceName="people/me",
            personFields=DEFAULT_PERSON_FIELDS,
            pageSize=25,
        )
        service.otherContacts.return_value.list.assert_called_once_with(
            readMask=DEFAULT_OTHER_CONTACTS_READ_MASK,
            pageSize=25,
            pageToken="other-page",
        )
        assert result == {
            "contacts": [{"resourceName": "people/c123"}],
            "otherContacts": [{"resourceName": "otherContacts/c456"}],
            "nextPageToken": "next-page",
            "nextOtherContactsPageToken": "next-other-page",
            "totalPeople": 1,
            "totalItems": None,
        }
        assert client._build_service.call_count == 2

    @pytest.mark.asyncio
    async def test_list_contacts_can_skip_other_contacts(self):
        service = MagicMock()
        people = service.people.return_value
        connections = people.connections.return_value
        connections.list.return_value.execute.return_value = {"connections": [{"resourceName": "people/c123"}]}

        client = object.__new__(GoogleContactsClient)
        client._build_service = MagicMock(return_value=service)

        result = await client.list_contacts(max_results=25, include_other_contacts=False)

        assert result["contacts"] == [{"resourceName": "people/c123"}]
        assert result["otherContacts"] == []
        assert result["nextOtherContactsPageToken"] is None
        service.otherContacts.return_value.list.assert_not_called()
        client._build_service.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_list_other_contacts_returns_normalized_payload(self):
        service = MagicMock()
        service.otherContacts.return_value.list.return_value.execute.return_value = {
            "otherContacts": [{"resourceName": "otherContacts/c456"}],
            "nextPageToken": "next-other-page",
            "totalSize": 1,
        }

        client = object.__new__(GoogleContactsClient)
        client._build_service = MagicMock(return_value=service)

        result = await client.list_other_contacts(
            max_results=25,
            read_mask=DEFAULT_OTHER_CONTACTS_READ_MASK,
            page_token="page",
        )

        service.otherContacts.return_value.list.assert_called_once_with(
            readMask=DEFAULT_OTHER_CONTACTS_READ_MASK,
            pageSize=25,
            pageToken="page",
        )
        assert result == {
            "otherContacts": [{"resourceName": "otherContacts/c456"}],
            "nextOtherContactsPageToken": "next-other-page",
            "totalSize": 1,
        }
        client._build_service.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_concurrent_requests_use_separate_services(self):
        services = []

        def _make_service():
            service = MagicMock()
            service.people.return_value.connections.return_value.list.return_value.execute.return_value = {
                "connections": [{"resourceName": "people/c123"}]
            }
            service.otherContacts.return_value.list.return_value.execute.return_value = {
                "otherContacts": [{"resourceName": "otherContacts/c456"}]
            }
            service.people.return_value.get.return_value.execute.return_value = {"resourceName": "people/c123"}
            services.append(service)
            return service

        client = object.__new__(GoogleContactsClient)
        client._build_service = MagicMock(side_effect=_make_service)

        list_result, get_result = await asyncio.gather(
            client.list_contacts(max_results=25),
            client.get_contact("people/c123"),
        )

        assert list_result["contacts"] == [{"resourceName": "people/c123"}]
        assert get_result == {"resourceName": "people/c123"}
        assert client._build_service.call_count == 3
        assert len({id(service) for service in services}) == 3
        assert sum(service.people.return_value.connections.return_value.list.call_count for service in services) == 1
        assert sum(service.otherContacts.return_value.list.call_count for service in services) == 1
        assert sum(service.people.return_value.get.call_count for service in services) == 1
        used_for_get = next(service for service in services if service.people.return_value.get.call_count == 1)
        used_for_get.people.return_value.get.assert_called_once_with(
            resourceName="people/c123",
            personFields=DEFAULT_PERSON_FIELDS,
        )

    @pytest.mark.asyncio
    async def test_get_contact_requires_people_resource_name(self):
        client = object.__new__(GoogleContactsClient)

        with pytest.raises(ValueError, match="people/"):
            await client.get_contact("c123")


class TestGoogleContactsServerTools:
    @pytest.mark.asyncio
    async def test_contacts_list_contacts_delegates_to_client(self):
        mock_client = AsyncMock()
        mock_client.list_contacts = AsyncMock(return_value={"contacts": []})

        with patch.object(contacts_server, "_client", mock_client, create=True):
            result = await contacts_server.contacts_list_contacts(max_results=10)

        assert result == {"contacts": []}
        mock_client.list_contacts.assert_awaited_once_with(
            max_results=10,
            person_fields=DEFAULT_PERSON_FIELDS,
            page_token=None,
            include_other_contacts=True,
            other_contacts_page_token=None,
            other_contacts_read_mask=DEFAULT_OTHER_CONTACTS_READ_MASK,
        )

    @pytest.mark.asyncio
    async def test_contacts_get_contact_delegates_to_client(self):
        mock_client = AsyncMock()
        mock_client.get_contact = AsyncMock(return_value={"resourceName": "people/c123"})

        with patch.object(contacts_server, "_client", mock_client, create=True):
            result = await contacts_server.contacts_get_contact("people/c123")

        assert result == {"resourceName": "people/c123"}
        mock_client.get_contact.assert_awaited_once_with(
            resource_name="people/c123",
            person_fields=DEFAULT_PERSON_FIELDS,
        )
