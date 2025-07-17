import json
from unittest.mock import MagicMock, AsyncMock
from types import SimpleNamespace

import pytest

from engine.llm_services.llm_service import CompletionService


def create_mock_message(role="assistant", content="Test response", tool_calls=None):
    """Helper function to create mock messages with consistent structure."""
    if tool_calls is None:
        tool_calls = []

    return SimpleNamespace(
        role=role,
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda: {
            "role": role,
            "content": content,
            "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in tool_calls],
        },
    )


def create_mock_llm_response(message):
    """Helper function to create mock LLM responses."""
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def create_mock_tool_call(tool_id="1", tool_name="test_tool", arguments=None):
    """Helper function to create mock tool calls."""
    if arguments is None:
        arguments = {"test_property": "Test value"}

    return SimpleNamespace(
        id=tool_id,
        function=SimpleNamespace(name=tool_name, arguments=json.dumps(arguments)),
        type="function",
        model_dump=lambda: {
            "id": tool_id,
            "function": {"name": tool_name, "arguments": json.dumps(arguments)},
            "type": "function",
        },
    )


@pytest.fixture
def mock_llm_service():
    """Basic mock LLM service fixture."""
    mock_llm_service = MagicMock(spec=CompletionService)
    mock_llm_service._model_name = "test_model"

    message = create_mock_message()
    response = create_mock_llm_response(message)

    mock_llm_service.afunction_call = AsyncMock(return_value=response)
    return mock_llm_service


@pytest.fixture
def mock_llm_service_with_tool_calls():
    """Mock LLM service that returns tool calls."""
    mock_llm_service = MagicMock(spec=CompletionService)
    mock_llm_service._model_name = "test_model"

    tool_call = create_mock_tool_call()
    message = create_mock_message(content="Tool response", tool_calls=[tool_call])
    response = create_mock_llm_response(message)

    mock_llm_service.afunction_call = AsyncMock(return_value=response)
    return mock_llm_service


@pytest.fixture
def mock_llm_service_sequential():
    """Mock LLM service that returns different responses on subsequent calls."""
    mock_llm_service = MagicMock(spec=CompletionService)
    mock_llm_service._model_name = "test_model"

    # First call: with tool calls
    tool_call = create_mock_tool_call()
    message_with_tools = create_mock_message(content="Tool response", tool_calls=[tool_call])
    response_with_tools = create_mock_llm_response(message_with_tools)

    # Second call: final response
    message_final = create_mock_message(content="Final response", tool_calls=[])
    response_final = create_mock_llm_response(message_final)

    mock_llm_service.afunction_call = AsyncMock(side_effect=[response_with_tools, response_final])
    return mock_llm_service
