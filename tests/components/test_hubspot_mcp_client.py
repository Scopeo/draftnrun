from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import engine.components.tools.hubspot_mcp.server as hubspot_server
from ada_backend.database.models import UIComponent
from engine.components.tools.hubspot_mcp.client import HubSpotClient
from engine.components.tools.hubspot_mcp_tool import HUBSPOT_DEFAULT_TOOL_NAMES
from engine.components.tools.mcp.shared import MCPToolInputs


@pytest.fixture
def client():
    return HubSpotClient("test-access-token")


@pytest.mark.asyncio
async def test_get_token_hubspot_metadata_returns_user_data(client):
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {
        "user": "owner@example.com",
        "user_id": 42,
        "hub_id": 123456,
        "hub_domain": "example.hubspot.com",
        "token_type": "bearer",
    }

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_response
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)

    with patch("engine.components.tools.hubspot_mcp.client.httpx.AsyncClient", return_value=mock_http_client):
        result = await client.get_token_hubspot_metadata()

    assert result["user"] == "owner@example.com"
    assert result["user_id"] == 42
    assert result["hub_id"] == 123456
    mock_http_client.get.assert_called_once_with("/oauth/v1/access-tokens/test-access-token")


@pytest.mark.asyncio
async def test_get_token_hubspot_metadata_raises_on_error(client):
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "Unauthorized"}

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_response
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)

    with patch("engine.components.tools.hubspot_mcp.client.httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(RuntimeError, match="401"):
            await client.get_token_hubspot_metadata()


@pytest.mark.asyncio
async def test_get_token_hubspot_metadata_falls_back_to_text_on_non_json_error(client):
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError("No JSON")
    mock_response.text = "Internal Server Error"

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_response
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)

    with patch("engine.components.tools.hubspot_mcp.client.httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(RuntimeError, match="Internal Server Error"):
            await client.get_token_hubspot_metadata()


@pytest.mark.asyncio
async def test_auth_get_current_user_tool():
    expected = {
        "user": "owner@example.com",
        "user_id": 42,
        "hub_id": 123456,
        "hub_domain": "example.hubspot.com",
    }
    mock_client = AsyncMock()
    mock_client.get_token_hubspot_metadata.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.auth_get_current_user()

    assert result == expected
    mock_client.get_token_hubspot_metadata.assert_called_once()


@pytest.mark.asyncio
async def test_notes_update_tool():
    expected = {"id": "note-123", "properties": {"hs_note_body": "Updated body"}}
    mock_client = AsyncMock()
    mock_client.request.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.notes_update(
            objectId="note-123",
            properties=hubspot_server.NoteProperties(
                hs_note_body="Updated body",
                hs_timestamp="2026-02-27T10:00:00Z",
            ),
        )

    assert result == expected
    mock_client.request.assert_called_once_with(
        "patch",
        "/crm/v3/objects/notes/note-123",
        json={
            "properties": {
                "hs_note_body": "Updated body",
                "hs_timestamp": "2026-02-27T10:00:00Z",
            }
        },
    )


def test_notes_update_in_default_tools():
    assert "notes_update" in HUBSPOT_DEFAULT_TOOL_NAMES


def test_mcp_tool_inputs_ports_are_exposed():
    tool_name_extra = MCPToolInputs.model_fields["tool_name"].json_schema_extra
    tool_arguments_extra = MCPToolInputs.model_fields["tool_arguments"].json_schema_extra

    assert tool_name_extra == {"is_tool_input": False}
    assert tool_arguments_extra is not None
    assert tool_arguments_extra["is_tool_input"] is False
    assert tool_arguments_extra["ui_component"] == UIComponent.JSON_TEXTAREA
