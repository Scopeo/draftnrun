from unittest.mock import MagicMock, patch, AsyncMock
import json
import pytest
import pytest_asyncio
from httpx import HTTPError

from engine.agent.tools.api_call_tool import APICallTool, API_CALL_TOOL_DESCRIPTION
from engine.agent.agent import AgentPayload, ChatMessage, ComponentAttributes
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest_asyncio.fixture
async def api_tool(mock_trace_manager):
    """Create an API call tool instance with proper async cleanup."""
    tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_api_tool"),
        endpoint="https://api.example.com/test",
        method="GET",
        headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"},
        timeout=30,
        fixed_parameters={"api_version": "v2", "format": "json", "language": "en"},
    )
    yield tool
    # Cleanup: ensure any lingering HTTP connections are closed
    import asyncio

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
    assert api_tool.endpoint == "https://api.example.com/test"
    assert api_tool.method == "GET"
    assert api_tool.headers == {"Content-Type": "application/json", "Authorization": "Bearer test_token"}
    assert api_tool.timeout == 30
    assert api_tool.fixed_parameters == {"api_version": "v2", "format": "json", "language": "en"}
    assert api_tool.tool_description == API_CALL_TOOL_DESCRIPTION


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_with_fixed_and_dynamic_params(mock_client_class, api_tool, mock_response):
    # Dynamic parameters provided by LLM
    dynamic_params = {"query": "test", "page": 1, "limit": 10, "filter": "active", "sort": "date"}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call(**dynamic_params)

    # Verify all parameters are included
    expected_params = {
        "api_version": "v2",  # Fixed
        "format": "json",  # Fixed
        "language": "en",  # Fixed
        "query": "test",  # Dynamic
        "page": 1,  # Dynamic
        "limit": 10,  # Dynamic
        "filter": "active",  # Dynamic
        "sort": "date",  # Dynamic
    }

    mock_client.request.assert_called_once_with(
        url="https://api.example.com/test",
        method="GET",
        headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"},
        timeout=30,
        params=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_post_with_fixed_and_dynamic_params(mock_client_class, api_tool, mock_response):
    # Change method to POST
    api_tool.method = "POST"

    # Dynamic parameters provided by LLM
    dynamic_params = {"data": {"name": "test", "value": 123}}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call(**dynamic_params)

    # Verify all parameters are included
    expected_params = {
        "api_version": "v2",  # Fixed
        "format": "json",  # Fixed
        "language": "en",  # Fixed
        "data": {"name": "test", "value": 123},  # Dynamic
    }

    mock_client.request.assert_called_once_with(
        url="https://api.example.com/test",
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"},
        timeout=30,
        json=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_with_only_fixed_params(mock_client_class, api_tool, mock_response):
    # Test with only fixed parameters

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call()

    expected_params = {"api_version": "v2", "format": "json", "language": "en"}

    mock_client.request.assert_called_once_with(
        url="https://api.example.com/test",
        method="GET",
        headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"},
        timeout=30,
        params=expected_params,
    )

    assert result["status_code"] == 200
    assert result["data"] == {"data": "test_data"}
    assert result["success"] is True


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_post_with_empty_params(mock_client_class, mock_trace_manager, mock_response):
    # Test POST with no parameters (should still send empty JSON)
    api_tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(
            component_instance_name="test_api_tool",
        ),
        endpoint="https://api.example.com/test",
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call()

    mock_client.request.assert_called_once_with(
        url="https://api.example.com/test",
        method="POST",
        headers={"Content-Type": "application/json"},
        timeout=30,
        json={},  # Empty JSON should still be sent for POST
    )

    assert result["status_code"] == 200
    assert result["success"] is True


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_get_with_empty_params(mock_client_class, mock_trace_manager, mock_response):
    # Test GET with no parameters (should not send params)
    api_tool = APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(
            component_instance_name="test_api_tool",
        ),
        endpoint="https://api.example.com/test",
        method="GET",
        headers={"Content-Type": "application/json"},
    )

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call()

    mock_client.request.assert_called_once_with(
        url="https://api.example.com/test",
        method="GET",
        headers={"Content-Type": "application/json"},
        timeout=30,
        # No params should be included for GET with empty parameters
    )

    assert result["status_code"] == 200
    assert result["success"] is True


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_error_handling(mock_client_class, api_tool):
    mock_client = AsyncMock()
    mock_client.request.side_effect = HTTPError("API Error")
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call()

    assert result["success"] is False
    assert result["error"] == "API Error"
    assert result["status_code"] is None


@pytest.mark.anyio
@patch("httpx.AsyncClient")
async def test_make_api_call_non_json_response(mock_client_class, api_tool):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "plain text response"
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    mock_response.headers = {"Content-Type": "text/plain"}

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_class.return_value.__aenter__.return_value = mock_client

    result = await api_tool.make_api_call()

    assert result["status_code"] == 200
    assert result["data"] == {"text": "plain text response"}
    assert result["success"] is True


@pytest.mark.anyio
async def test_run_without_trace_with_dynamic_params(api_tool):
    agent_input = AgentPayload(messages=[ChatMessage(role="user", content="test")])
    dynamic_params = {"query": "test", "page": 1, "filter": "active"}

    with patch.object(api_tool, "make_api_call") as mock_make_api_call:
        mock_make_api_call.return_value = {
            "status_code": 200,
            "data": {"result": "success"},
            "headers": {"Content-Type": "application/json"},
            "success": True,
        }

        result = await api_tool._run_without_trace(agent_input, **dynamic_params)

        assert isinstance(result, AgentPayload)
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert "result" in result.messages[0].content
        assert result.artifacts["api_response"]["success"] is True
        mock_make_api_call.assert_called_once_with(**dynamic_params)


@pytest.mark.anyio
async def test_run_without_trace_error(api_tool):
    agent_input = AgentPayload(messages=[ChatMessage(role="user", content="test")])

    with patch.object(api_tool, "make_api_call") as mock_make_api_call:
        mock_make_api_call.return_value = {"status_code": 500, "error": "Internal Server Error", "success": False}

        result = await api_tool._run_without_trace(agent_input)

        assert isinstance(result, AgentPayload)
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert "API call failed" in result.messages[0].content
        assert result.artifacts["api_response"]["success"] is False
