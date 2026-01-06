import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.ai_agent import AIAgent
from engine.components.tools.remote_mcp_tool import RemoteMCPTool
from engine.components.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def mock_llm_service():
    mock_service = MagicMock(spec=CompletionService)
    mock_service._model_name = "test_model"
    mock_service._model_id = None
    return mock_service


@pytest.fixture
def base_tool_description():
    return ToolDescription(
        name="react_agent",
        description="Base react agent",
        tool_properties={},
        required_tool_properties=[],
    )


def build_mock_tool_calls():
    mock_tool_call = MagicMock()
    mock_tool_call.id = "1"
    mock_tool_call_function = MagicMock()
    mock_tool_call_function.name = "remote_one"
    mock_tool_call_function.arguments = json.dumps({"query": "abc"})
    mock_tool_call.function = mock_tool_call_function

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    mock_message.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "1",
                "type": "function",
                "function": {"name": "remote_one", "arguments": json.dumps({"query": "abc"})},
            }
        ],
    }

    return MagicMock(choices=[MagicMock(message=mock_message)])


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_react_agent_expands_mcp_tools(
    agent_calls_mock, get_span_mock, monkeypatch, mock_trace_manager, mock_llm_service, base_tool_description
):
    mock_tool_one = MagicMock()
    mock_tool_one.name = "remote_one"
    mock_tool_one.description = "First remote"
    mock_tool_one.inputSchema = {"properties": {"query": {"type": "string"}}, "required": ["query"]}

    mock_tool_two = MagicMock()
    mock_tool_two.name = "remote_two"
    mock_tool_two.description = "Second remote"
    mock_tool_two.inputSchema = {"properties": {"id": {"type": "string"}}, "required": ["id"]}

    mock_list_result = MagicMock()
    mock_list_result.tools = [mock_tool_one, mock_tool_two]

    async def fake_list(self):
        return mock_list_result

    async def fake_call(self, tool_name, arguments):
        assert tool_name == "remote_one"
        fake_result = MagicMock()
        fake_result.content = [MagicMock(text="result for remote_one")]
        fake_result.isError = False
        return fake_result

    monkeypatch.setattr(RemoteMCPTool, "_list_tools_with_sdk", fake_list)
    monkeypatch.setattr(RemoteMCPTool, "_call_tool_with_sdk", fake_call)

    import asyncio

    remote_tool = asyncio.run(
        RemoteMCPTool.from_mcp_server(
            trace_manager=mock_trace_manager,
            component_attributes=ComponentAttributes(component_instance_name="remote-mcp"),
            server_url="https://mcp.example.com",
        )
    )

    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    mock_llm_service.function_call_async = AsyncMock(return_value=build_mock_tool_calls())

    react_agent = AIAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="ReactAgent"),
        trace_manager=mock_trace_manager,
        tool_description=base_tool_description,
        agent_tools=[remote_tool],
        allow_tool_shortcuts=True,
    )

    # Mock _process_tool_calls to return the correct format
    async def mock_process_tool_calls(*args, **kwargs):
        tool_outputs = {
            "1": AgentPayload(messages=[ChatMessage(role="assistant", content="result for remote_one")], is_final=True)
        }
        processed_tool_calls = [
            {
                "id": "1",
                "type": "function",
                "function": {"name": "remote_one", "arguments": json.dumps({"query": "abc"})},
            }
        ]
        return tool_outputs, processed_tool_calls

    with patch.object(react_agent, "_process_tool_calls", side_effect=mock_process_tool_calls):
        input_payload = AgentPayload(messages=[ChatMessage(role="user", content="Hello")])
        output = react_agent.run_sync(input_payload)

    tools_passed = mock_llm_service.function_call_async.call_args.kwargs["tools"]
    assert len(tools_passed) == 2
    assert any(tool.name == "remote_one" for tool in tools_passed)
    assert output.last_message.content == "result for remote_one"
    assert output.is_final
