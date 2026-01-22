"""
Simple tests for Nango client.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from ada_backend.services.integration_service import generate_nango_end_user_id
from ada_backend.services.nango_client import NangoClient


def _async_client(*, get: AsyncMock | None = None, post: AsyncMock | None = None):
    client = MagicMock()
    client.get = get or AsyncMock()
    client.post = post or AsyncMock()
    client.delete = AsyncMock()
    client.request = AsyncMock()
    return client


def test_generate_nango_end_user_id():
    """Test end_user_id format for OAuth connections."""
    project_id = uuid4()
    provider_config_key = "slack"

    end_user_id = generate_nango_end_user_id(project_id, provider_config_key)

    assert end_user_id == f"proj_{project_id}_{provider_config_key}"


@patch("ada_backend.services.nango_client.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_health_check_success(mock_async_client):
    """Test successful health check."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_async_client.return_value = _async_client(get=AsyncMock(return_value=mock_response))

    client = NangoClient(
        base_url="http://test-nango:3003",
        secret_key="test-secret-key",
    )

    result = await client.health_check()

    assert result is True


@patch("ada_backend.services.nango_client.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_health_check_failure(mock_async_client):
    """Test failed health check."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_async_client.return_value = _async_client(get=AsyncMock(return_value=mock_response))

    client = NangoClient(
        base_url="http://test-nango:3003",
        secret_key="test-secret-key",
    )

    result = await client.health_check()

    assert result is False


@patch("ada_backend.services.nango_client.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_list_connections_filters_client_side(mock_async_client):
    """
    Verify that list_connections fetches ALL items and filters them in memory (client-side).
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "connections": [
            {"connection_id": "target", "provider_config_key": "slack", "end_user_id": "target_user"},
            {"connection_id": "wrong_provider", "provider_config_key": "github", "end_user_id": "target_user"},
            {"connection_id": "wrong_user", "provider_config_key": "slack", "end_user_id": "other_user"},
        ]
    }
    mock_client = _async_client(get=AsyncMock(return_value=mock_response))
    mock_async_client.return_value = mock_client

    nango_client = NangoClient(
        base_url="http://test-nango:3003",
        secret_key="test-secret-key",
    )

    connections = await nango_client.list_connections(provider_config_key="slack", end_user_id="target_user")

    assert len(connections) == 1
    assert connections[0]["connection_id"] == "target"

    _, kwargs = mock_client.get.call_args
    assert "params" not in kwargs or not kwargs["params"]


@patch("ada_backend.services.nango_client.httpx.AsyncClient")
@pytest.mark.asyncio
async def test_list_connections_returns_empty_list(mock_async_client):
    """Returns empty list when no connections are found."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"connections": []}
    mock_async_client.return_value = _async_client(get=AsyncMock(return_value=mock_response))

    nango_client = NangoClient(
        base_url="http://test-nango:3003",
        secret_key="test-secret-key",
    )

    connections = await nango_client.list_connections(provider_config_key="slack", end_user_id="proj_x_int_y")

    assert connections == []
