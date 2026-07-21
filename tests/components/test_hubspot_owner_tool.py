import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from engine.components.tools.hubspot_owner_tool import (
    HUBSPOT_CONTACTS_SEARCH_ENDPOINT,
    HUBSPOT_OWNER_TOOL_DESCRIPTION,
    HubSpotOwnerInputs,
    HubSpotOwnerOutputs,
    HubSpotOwnerTool,
)
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

OWNER_RESPONSE = {
    "id": "1361098942",
    "email": "benjamin.attal@novair.fr",
    "type": "PERSON",
    "firstName": "Benjamin",
    "lastName": "ATTAL",
    "userId": None,
    "userIdIncludingInactive": None,
    "createdAt": "2026-03-18T08:51:56.541Z",
    "updatedAt": "2026-05-04T09:52:17.667Z",
    "archived": False,
}


def _hubspot_owner_tool() -> HubSpotOwnerTool:
    return HubSpotOwnerTool(
        trace_manager=MagicMock(spec=TraceManager),
        component_attributes=ComponentAttributes(component_instance_name="hubspot_owner"),
        method="GET",
        timeout=30,
    )


def test_hubspot_owner_tool_initialization():
    tool = _hubspot_owner_tool()

    assert tool.method == "GET"
    assert tool.timeout == 30
    assert tool.tool_description == HUBSPOT_OWNER_TOOL_DESCRIPTION


@patch("httpx.AsyncClient")
def test_hubspot_owner_tool_calls_owner_endpoint(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = OWNER_RESPONSE
    mock_response.text = json.dumps(OWNER_RESPONSE)
    mock_response.headers = {"Content-Type": "application/json"}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    inputs = HubSpotOwnerInputs(
        headers='{"Authorization": "Bearer hubspot_token"}',
        owner_id="1361098942",
    )
    result = asyncio.run(_hubspot_owner_tool()._run_without_io_trace(inputs))

    mock_client.request.assert_called_once_with(
        url="https://api.hubapi.com/crm/v3/owners/1361098942",
        method="GET",
        headers={"Authorization": "Bearer hubspot_token"},
        timeout=30,
    )
    assert isinstance(result, HubSpotOwnerOutputs)
    assert result.success is True
    assert result.status_code == 200


def test_hubspot_owner_tool_flattens_owner_data_to_root_outputs():
    tool = _hubspot_owner_tool()
    inputs = HubSpotOwnerInputs(
        headers={"Authorization": "Bearer hubspot_token"},
        owner_id="1361098942",
    )

    with patch.object(tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": OWNER_RESPONSE,
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }

        result = asyncio.run(tool._run_without_io_trace(inputs))

    mock_make_api_call.assert_called_once_with(
        headers={"Authorization": "Bearer hubspot_token"},
        fixed_parameters={},
        endpoint="https://api.hubapi.com/crm/v3/owners/1361098942",
    )
    assert result.output == json.dumps(OWNER_RESPONSE, indent=2)
    assert result.id == "1361098942"
    assert result.email == "benjamin.attal@novair.fr"
    assert result.firstName == "Benjamin"
    assert result.lastName == "ATTAL"
    assert result.archived is False


@patch("httpx.AsyncClient")
def test_hubspot_owner_tool_fetches_additional_properties_via_async_httpx(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "properties": {
                    "phone": "+33123456789",
                    "company": "Novair",
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    tool = _hubspot_owner_tool()
    inputs = HubSpotOwnerInputs(
        headers={"Authorization": "Bearer hubspot_token"},
        owner_id="1361098942",
        additional_properties={"phone": None, "company": None},
    )

    with patch.object(tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": OWNER_RESPONSE.copy(),
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }
        result = asyncio.run(tool._run_without_io_trace(inputs))

    mock_client.request.assert_called_once_with(
        method="POST",
        url=HUBSPOT_CONTACTS_SEARCH_ENDPOINT,
        headers={"Authorization": "Bearer hubspot_token"},
        timeout=30,
        json={
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": "benjamin.attal@novair.fr",
                        }
                    ]
                }
            ],
            "properties": ["phone", "company"],
            "limit": 1,
        },
    )
    assert result.phone == "+33123456789"
    assert result.company == "Novair"


def test_hubspot_owner_tool_additional_properties_defaults_when_owner_has_no_email():
    tool = _hubspot_owner_tool()
    owner_without_email = {**OWNER_RESPONSE, "email": None}
    inputs = HubSpotOwnerInputs(
        headers={"Authorization": "Bearer hubspot_token"},
        owner_id="1361098942",
        additional_properties={"phone": None},
    )

    with patch.object(tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": owner_without_email,
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }
        with patch("httpx.AsyncClient") as mock_client_class:
            result = asyncio.run(tool._run_without_io_trace(inputs))

    mock_client_class.assert_not_called()
    assert result.phone is None


@patch("httpx.AsyncClient")
def test_hubspot_owner_tool_additional_properties_raises_on_invalid_json_response(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    tool = _hubspot_owner_tool()
    inputs = HubSpotOwnerInputs(
        headers={"Authorization": "Bearer hubspot_token"},
        owner_id="1361098942",
        additional_properties={"phone": None},
    )

    with patch.object(tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": OWNER_RESPONSE.copy(),
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }
        with pytest.raises(ValueError, match="HubSpot request failed"):
            asyncio.run(tool._run_without_io_trace(inputs))


@patch("httpx.AsyncClient")
def test_hubspot_owner_tool_additional_properties_raises_on_http_error(mock_client_class):
    mock_client = AsyncMock()
    mock_client.request.side_effect = httpx.ConnectError("connection failed")
    mock_client_class.return_value.__aenter__.return_value = mock_client

    tool = _hubspot_owner_tool()
    inputs = HubSpotOwnerInputs(
        headers={"Authorization": "Bearer hubspot_token"},
        owner_id="1361098942",
        additional_properties={"phone": None},
    )

    with patch.object(tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": OWNER_RESPONSE.copy(),
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }
        with pytest.raises(ValueError, match="HubSpot request failed"):
            asyncio.run(tool._run_without_io_trace(inputs))
