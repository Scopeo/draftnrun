import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import HTTPError

from engine.components.tools.api_call_tool import (
    API_CALL_TOOL_DESCRIPTION,
    APICallTool,
    APICallToolInputs,
    APICallToolOutputs,
)
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

ENDPOINT = "https://api.example.com/test"
HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer test_token"}
FIXED_PARAMS = {"api_version": "v2", "format": "json", "language": "en"}


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest_asyncio.fixture
async def api_tool(mock_trace_manager):
    tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_api_tool"),
        method="GET",
        timeout=30,
    )
    yield tool
    await asyncio.sleep(0.1)


@pytest.fixture
def mock_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": "test_data"}
    mock.text = '{"data": "test_data"}'
    mock.headers = {"Content-Type": "application/json"}
    return mock


def test_api_tool_initialization(api_tool):
    assert api_tool.method == "GET"
    assert api_tool.timeout == 30
    assert api_tool.tool_description == API_CALL_TOOL_DESCRIPTION


@patch("httpx.AsyncClient")
def test_make_api_call_with_fixed_and_dynamic_params(mock_client_class, api_tool, mock_response):
    dynamic_params = {"query": "test", "page": 1, "limit": 10, "sort": "date"}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(
        api_tool.make_api_call(headers=HEADERS, fixed_parameters=FIXED_PARAMS, endpoint=ENDPOINT, **dynamic_params)
    )

    expected_params = {
        "api_version": "v2",
        "format": "json",
        "language": "en",
        "query": "test",
        "page": 1,
        "limit": 10,
        "sort": "date",
    }

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="GET",
        headers=HEADERS,
        timeout=30,
        params=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@patch("httpx.AsyncClient")
def test_make_api_call_post_with_fixed_and_dynamic_params(mock_client_class, api_tool, mock_response):
    api_tool.method = "POST"
    dynamic_params = {"data": {"name": "test", "value": 123}}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(
        api_tool.make_api_call(headers=HEADERS, fixed_parameters=FIXED_PARAMS, endpoint=ENDPOINT, **dynamic_params)
    )

    expected_params = {
        "api_version": "v2",
        "format": "json",
        "language": "en",
        "data": {"name": "test", "value": 123},
    }

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="POST",
        headers=HEADERS,
        timeout=30,
        json=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@patch("httpx.AsyncClient")
def test_make_api_call_with_only_fixed_params(mock_client_class, api_tool, mock_response):
    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(
        api_tool.make_api_call(headers=HEADERS, fixed_parameters=FIXED_PARAMS, endpoint=ENDPOINT)
    )

    expected_params = {"api_version": "v2", "format": "json", "language": "en"}

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="GET",
        headers=HEADERS,
        timeout=30,
        params=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@patch("httpx.AsyncClient")
def test_make_api_call_post_with_empty_params(mock_client_class, mock_trace_manager, mock_response):
    api_tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_api_tool"),
        method="POST",
        timeout=30,
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(
        api_tool.make_api_call(
            headers={"Content-Type": "application/json"},
            fixed_parameters={},
            endpoint=ENDPOINT,
        )
    )

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="POST",
        headers={"Content-Type": "application/json"},
        timeout=30,
        json={},
    )

    assert result["status_code"] == 200
    assert result["success"] is True


@patch("httpx.AsyncClient")
def test_make_api_call_get_with_empty_params(mock_client_class, mock_trace_manager, mock_response):
    api_tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_api_tool"),
        method="GET",
        timeout=30,
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(
        api_tool.make_api_call(
            headers={"Content-Type": "application/json"},
            fixed_parameters={},
            endpoint=ENDPOINT,
        )
    )

    # No params for GET with empty parameters
    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="GET",
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    assert result["status_code"] == 200
    assert result["success"] is True


@patch("httpx.AsyncClient")
def test_make_api_call_error_handling(mock_client_class, api_tool):
    mock_client = AsyncMock()
    mock_client.request.side_effect = HTTPError("API Error")
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(api_tool.make_api_call(headers={}, fixed_parameters={}, endpoint=ENDPOINT))

    assert result["success"] is False
    assert result["error"] == "API Error"
    assert result["status_code"] is None


@patch("httpx.AsyncClient")
def test_make_api_call_non_json_response(mock_client_class, api_tool):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "plain text response"
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    mock_response.headers = {"Content-Type": "text/plain"}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(api_tool.make_api_call(headers={}, fixed_parameters={}, endpoint=ENDPOINT))

    assert result["status_code"] == 200
    assert result["data"] == {"text": "plain text response"}
    assert result["success"] is True


def test_run_without_io_trace_with_dynamic_params(api_tool):
    inputs = APICallToolInputs(
        endpoint=ENDPOINT,
        headers=HEADERS,
        fixed_parameters=FIXED_PARAMS,
        query="test",
        page=1,
    )

    with patch.object(api_tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": {"result": "success"},
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }

        result = asyncio.run(api_tool._run_without_io_trace(inputs))

        assert isinstance(result, APICallToolOutputs)
        assert result.success is True
        assert result.status_code == 200
        assert "result" in result.output
        mock_make_api_call.assert_called_once_with(
            headers=HEADERS,
            fixed_parameters=FIXED_PARAMS,
            endpoint=ENDPOINT,
            query="test",
            page=1,
        )


def test_run_without_io_trace_error(api_tool):
    inputs = APICallToolInputs(
        endpoint=ENDPOINT,
        headers=HEADERS,
        fixed_parameters=FIXED_PARAMS,
    )

    with patch.object(api_tool, "make_api_call", new_callable=AsyncMock) as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 500,
            "error": "Internal Server Error",
            "success": False,
        }

        result = asyncio.run(api_tool._run_without_io_trace(inputs))

        assert isinstance(result, APICallToolOutputs)
        assert result.success is False
        assert result.status_code == 500
        assert "API call failed" in result.output


@patch("httpx.AsyncClient")
def test_api_call_tool_with_string_headers_and_fixed_params(mock_client_class, mock_trace_manager, mock_response):
    """String headers and fixed_parameters are parsed in _run_without_io_trace."""
    tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_api_tool"),
        method="GET",
        timeout=30,
    )
    inputs = APICallToolInputs(
        endpoint=ENDPOINT,
        headers='{"Content-Type": "application/json", "Authorization": "Bearer test_token"}',
        fixed_parameters='{"api_version": "v2", "format": "json"}',
        query="test",
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(tool._run_without_io_trace(inputs))

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="GET",
        headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"},
        timeout=30,
        params={"api_version": "v2", "format": "json", "query": "test"},
    )

    assert isinstance(result, APICallToolOutputs)
    assert result.status_code == 200
    assert result.success is True


@patch("httpx.AsyncClient")
def test_api_call_tool_with_dict_headers_and_fixed_params(mock_client_class, mock_trace_manager, mock_response):
    tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="api_call_tool"),
        method="POST",
        timeout=30,
    )
    inputs = APICallToolInputs(
        endpoint=ENDPOINT,
        headers={"Content-Type": "application/json"},
        fixed_parameters={"api_version": "v2"},
        data={"name": "foo"},
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = asyncio.run(tool._run_without_io_trace(inputs))

    mock_client.request.assert_called_once_with(
        url=ENDPOINT,
        method="POST",
        headers={"Content-Type": "application/json"},
        timeout=30,
        json={"api_version": "v2", "data": {"name": "foo"}},
    )

    assert isinstance(result, APICallToolOutputs)
    assert result.status_code == 200
    assert result.success is True
