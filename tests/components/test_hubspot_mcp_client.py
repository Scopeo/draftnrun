from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import engine.components.tools.hubspot_mcp.server as hubspot_server
from engine.components.tools.hubspot_mcp.client import HubSpotClient


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
