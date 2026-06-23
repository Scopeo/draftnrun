import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from engine.components.tools.hubspot_owner_tool import (
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
