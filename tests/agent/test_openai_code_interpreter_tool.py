import asyncio
from unittest.mock import MagicMock

import pytest

from engine.agent.agent import AgentPayload, ChatMessage, ToolDescription
from engine.agent.openai_code_interpreter_tool import (
    OpenAICodeInterpreterTool,
    DEFAULT_OPENAI_CODE_INTERPRETER_TOOL_DESCRIPTION,
)
from engine.llm_services.llm_service import CodeInterpreterService
from tests.mocks.trace_manager import MockTraceManager


@pytest.fixture
def mock_code_interpreter_service():
    """Create a mock CodeInterpreterService for testing."""
    service = MagicMock(spec=CodeInterpreterService)
    service._model_name = "gpt-4.1-mini"
    service.execute_code.return_value = "Code executed successfully. Output: Hello, World!"
    return service


@pytest.fixture
def openai_code_interpreter_tool(mock_code_interpreter_service):
    """Create an OpenAI Code Interpreter tool instance."""
    return OpenAICodeInterpreterTool(
        code_interpreter_service=mock_code_interpreter_service,
        trace_manager=MockTraceManager(project_name="test_project"),
        component_instance_name="test_code_interpreter",
    )


def test_openai_code_interpreter_tool_initialization(openai_code_interpreter_tool, mock_code_interpreter_service):
    """Test that the OpenAI Code Interpreter tool initializes correctly."""
    assert openai_code_interpreter_tool._code_interpreter_service == mock_code_interpreter_service
    assert openai_code_interpreter_tool.tool_description == DEFAULT_OPENAI_CODE_INTERPRETER_TOOL_DESCRIPTION
    assert openai_code_interpreter_tool.tool_description.name == "OpenAI_Code_Interpreter"


def test_default_tool_description():
    """Test the default tool description."""
    desc = DEFAULT_OPENAI_CODE_INTERPRETER_TOOL_DESCRIPTION
    assert desc.name == "OpenAI_Code_Interpreter"
    assert "Execute Python code" in desc.description
    assert "code_prompt" in desc.tool_properties
    assert desc.required_tool_properties == ["code_prompt"]


@pytest.mark.asyncio
async def test_openai_code_interpreter_tool_with_code_prompt(
    openai_code_interpreter_tool, mock_code_interpreter_service
):
    """Test the OpenAI Code Interpreter tool with a code prompt parameter."""
    code_prompt = "import numpy as np\nprint(np.array([1, 2, 3]))"

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="Execute some code")])

    result = await openai_code_interpreter_tool._run_without_trace(input_payload, code_prompt=code_prompt)

    # Verify that the code interpreter service was called with the correct prompt
    mock_code_interpreter_service.execute_code.assert_called_once_with(code_prompt)

    # Verify the response structure
    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert result.messages[0].role == "assistant"
    assert "Code executed successfully" in str(result.messages[0].content)


@pytest.mark.asyncio
async def test_openai_code_interpreter_tool_with_message_content(
    openai_code_interpreter_tool, mock_code_interpreter_service
):
    """Test the OpenAI Code Interpreter tool using message content when no code_prompt is provided."""
    code_content = "print('Hello from message content!')"

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content=code_content)])

    result = await openai_code_interpreter_tool._run_without_trace(input_payload)

    # Verify that the code interpreter service was called with the message content
    mock_code_interpreter_service.execute_code.assert_called_once_with(code_content)

    # Verify the response structure
    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert result.messages[0].role == "assistant"
    assert "Code executed successfully" in str(result.messages[0].content)


@pytest.mark.asyncio
async def test_openai_code_interpreter_tool_no_valid_prompt(openai_code_interpreter_tool):
    """Test the OpenAI Code Interpreter tool behavior when no valid prompt is provided."""
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="")])

    with pytest.raises(ValueError, match="No valid code prompt provided"):
        await openai_code_interpreter_tool._run_without_trace(input_payload, code_prompt=None)


@pytest.mark.asyncio
async def test_openai_code_interpreter_tool_custom_description():
    """Test the OpenAI Code Interpreter tool with custom tool description."""
    custom_description = ToolDescription(
        name="Custom_Code_Interpreter",
        description="Custom code interpreter for testing",
        tool_properties={
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
        },
        required_tool_properties=["code"],
    )

    mock_service = MagicMock(spec=CodeInterpreterService)
    mock_service._model_name = "gpt-4o"
    mock_service.execute_code.return_value = "Custom execution result"

    tool = OpenAICodeInterpreterTool(
        code_interpreter_service=mock_service,
        trace_manager=MockTraceManager(project_name="test_project"),
        component_instance_name="custom_test",
        tool_description=custom_description,
    )

    assert tool.tool_description == custom_description
    assert tool.tool_description.name == "Custom_Code_Interpreter"


def test_openai_code_interpreter_tool_integration():
    """Test basic integration between the tool and service."""
    # This test doesn't require actual API calls, just verifies the integration
    service = MagicMock(spec=CodeInterpreterService)
    service._model_name = "gpt-4.1-mini"

    tool = OpenAICodeInterpreterTool(
        code_interpreter_service=service,
        trace_manager=MockTraceManager(project_name="test_project"),
        component_instance_name="integration_test",
    )

    assert tool._code_interpreter_service == service
    assert tool.component_instance_name == "integration_test"
