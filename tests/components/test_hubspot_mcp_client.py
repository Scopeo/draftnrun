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
async def test_crm_upsert_contact_by_email_creates_without_object_id():
    expected = {"vid": 123, "isNew": True}
    mock_client = AsyncMock()
    mock_client.request.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.crm_upsert_contact_by_email(
            properties=hubspot_server.ContactProperties(
                email="ada@example.com",
                firstname="Ada",
                lastname="Lovelace",
            ),
        )

    assert result == {"id": "123", "operation": "created"}
    mock_client.request.assert_called_once_with(
        "post",
        "/contacts/v1/contact/createOrUpdate/email/ada@example.com",
        json={
            "properties": [
                {"property": "email", "value": "ada@example.com"},
                {"property": "firstname", "value": "Ada"},
                {"property": "lastname", "value": "Lovelace"},
            ]
        },
    )


@pytest.mark.asyncio
async def test_crm_upsert_contact_by_email_updates_with_object_id():
    expected = {"id": "contact-123"}
    mock_client = AsyncMock()
    mock_client.request.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.crm_upsert_contact_by_email(
            objectId="contact-123",
            properties=hubspot_server.ContactProperties(
                email="ada@example.com",
                firstname="Ada",
            ),
        )

    assert result == {"id": "contact-123", "operation": "updated"}
    mock_client.request.assert_called_once_with(
        "patch",
        "/crm/v3/objects/contacts/contact-123",
        json={"properties": {"email": "ada@example.com", "firstname": "Ada"}},
    )


@pytest.mark.asyncio
async def test_notes_upsert_for_contact_creates_and_associates_note():
    expected = {"id": "note-123"}
    mock_client = AsyncMock()
    mock_client.request.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.notes_upsert_for_contact(
            contactId="contact-123",
            properties=hubspot_server.NoteProperties(
                hs_note_body="Created body",
                hs_timestamp="2026-02-27T10:00:00Z",
            ),
        )

    assert result == {"id": "note-123", "operation": "created", "contactId": "contact-123"}
    mock_client.request.assert_called_once_with(
        "post",
        "/crm/v3/objects/notes",
        json={
            "properties": {
                "hs_note_body": "Created body",
                "hs_timestamp": "2026-02-27T10:00:00Z",
            },
            "associations": [
                {
                    "to": {"id": "contact-123"},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 202,
                        }
                    ],
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_notes_upsert_for_contact_updates_existing_note():
    expected = {"id": "note-123"}
    mock_client = AsyncMock()
    mock_client.request.return_value = expected

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.notes_upsert_for_contact(
            contactId="contact-123",
            objectId="note-123",
            properties=hubspot_server.NoteProperties(
                hs_note_body="Updated body",
                hs_timestamp="2026-02-27T10:00:00Z",
            ),
        )

    assert result == {"id": "note-123", "operation": "updated", "contactId": "contact-123"}
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


@pytest.mark.asyncio
async def test_notes_upsert_for_contact_skips_empty_body():
    mock_client = AsyncMock()

    with patch("engine.components.tools.hubspot_mcp.server._client", mock_client, create=True):
        result = await hubspot_server.notes_upsert_for_contact(
            contactId="contact-123",
            skipIfBodyEmpty=True,
            properties=hubspot_server.NoteProperties(
                hs_note_body="   ",
                hs_timestamp="2026-02-27T10:00:00Z",
            ),
        )

    assert result == {"id": "", "operation": "skipped", "contactId": "contact-123"}
    mock_client.request.assert_not_called()


def test_hubspot_default_tools_include_upsert_helpers():
    assert "crm_upsert_contact_by_email" in HUBSPOT_DEFAULT_TOOL_NAMES
    assert "notes_upsert_for_contact" in HUBSPOT_DEFAULT_TOOL_NAMES
    assert "notes_update" not in HUBSPOT_DEFAULT_TOOL_NAMES


def test_mcp_tool_inputs_ports_are_exposed():
    tool_name_extra = MCPToolInputs.model_fields["tool_name"].json_schema_extra
    tool_arguments_extra = MCPToolInputs.model_fields["tool_arguments"].json_schema_extra

    assert tool_name_extra == {"is_tool_input": False}
    assert tool_arguments_extra is not None
    assert tool_arguments_extra["is_tool_input"] is False
    assert tool_arguments_extra["ui_component"] == UIComponent.JSON_TEXTAREA
