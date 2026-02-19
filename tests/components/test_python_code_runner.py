import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from engine.components.tools.python_code_runner import (
    PYTHON_CODE_RUNNER_TOOL_DESCRIPTION,
    PythonCodeRunner,
    PythonCodeRunnerToolInputs,
    PythonCodeRunnerToolOutputs,
)
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def mock_e2b_api_key():
    with patch("engine.components.tools.python_code_runner.settings") as mock_settings:
        mock_settings.E2B_API_KEY = "test_api_key"
        yield


@pytest.fixture
def python_code_runner_tool(mock_e2b_api_key, mock_trace_manager):
    return PythonCodeRunner(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_python_code_runner"),
        timeout=30,
    )


@pytest.fixture
def mock_sandbox():
    mock = AsyncMock()
    mock_execution = Mock()
    mock_execution.error = None
    mock_execution.results = []
    mock_execution.logs = Mock(stdout=["Hello, World!"], stderr=[])
    mock.run_code.return_value = mock_execution
    mock.files.list.return_value = []
    mock.kill.return_value = None
    return mock


def test_tool_initialization(python_code_runner_tool):
    """Test that the tool initializes correctly."""
    assert python_code_runner_tool.component_attributes.component_instance_name == "test_python_code_runner"
    assert python_code_runner_tool.sandbox_timeout == 30
    assert python_code_runner_tool.tool_description == PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
    assert python_code_runner_tool.tool_description.name == "python_code_runner"


def test_tool_description_structure():
    """Test that the tool description has the correct structure."""
    desc = PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
    assert desc.name == "python_code_runner"
    assert "Execute Python code in a secure sandbox environment" in desc.description
    assert "python_code" in desc.tool_properties
    assert desc.tool_properties["python_code"]["type"] == "string"
    assert "python_code" in desc.required_tool_properties


def test_sandbox_timeout_configuration():
    """Test that the tool respects the sandbox timeout configuration."""
    tool = PythonCodeRunner(
        trace_manager=MagicMock(spec=TraceManager),
        component_attributes=ComponentAttributes(component_instance_name="test_timeout"),
        timeout=10,
    )
    assert tool.sandbox_timeout == 10


def test_missing_api_key():
    """Test that the tool raises an error when E2B API key is not configured."""
    with pytest.MonkeyPatch().context() as m:
        m.setattr("settings.settings.E2B_API_KEY", None)

        tool = PythonCodeRunner(
            trace_manager=MagicMock(spec=TraceManager),
            component_attributes=ComponentAttributes(component_instance_name="test_no_api_key"),
        )
        with pytest.raises(ValueError, match="E2B API key not configured"):
            asyncio.run(tool.execute_python_code("print('test')"))


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_execute_python_code_success(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test successful Python code execution."""
    mock_get_tracing_span.return_value = None
    mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

    result, records = await python_code_runner_tool.execute_python_code("print('Hello, World!')")

    assert result["error"] is None
    assert result["stdout"] == ["Hello, World!"]
    assert result["stderr"] == []
    mock_sandbox.run_code.assert_called_once_with(code="print('Hello, World!')", timeout=30)
    mock_sandbox.kill.assert_called_once()


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_execute_python_code_with_error(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test Python code execution that returns an error."""
    mock_get_tracing_span.return_value = None
    mock_execution = Mock()
    mock_execution.error = Mock()
    mock_execution.error.__str__ = Mock(return_value="ZeroDivisionError: division by zero")
    mock_execution.results = []
    mock_execution.logs = Mock(stdout=[], stderr=[])
    mock_sandbox.run_code.return_value = mock_execution
    mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

    result, _ = await python_code_runner_tool.execute_python_code("1 / 0")

    assert result["error"] == "ZeroDivisionError: division by zero"
    mock_sandbox.kill.assert_called_once()


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_execute_python_code_sandbox_exception(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test that sandbox exceptions are caught and returned gracefully."""
    mock_get_tracing_span.return_value = None
    mock_sandbox.run_code.side_effect = Exception("Sandbox connection failed")
    mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

    result, records = await python_code_runner_tool.execute_python_code("print('test')")

    assert result["error"] == "Sandbox connection failed"
    assert result["results"] == []
    mock_sandbox.kill.assert_called_once()


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_execute_python_code_with_shared_sandbox(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test that a shared sandbox from tracing context is reused."""
    shared_sandbox = AsyncMock()
    mock_execution = Mock()
    mock_execution.error = None
    mock_execution.results = []
    mock_execution.logs = Mock(stdout=["Shared output"], stderr=[])
    shared_sandbox.run_code.return_value = mock_execution
    shared_sandbox.is_running.return_value = True
    shared_sandbox.files.list.return_value = []

    mock_params = Mock()
    mock_params.shared_sandbox = shared_sandbox
    mock_get_tracing_span.return_value = mock_params

    result, _ = await python_code_runner_tool.execute_python_code("print('test')")

    assert result["stdout"] == ["Shared output"]
    mock_sandbox_class.create.assert_not_called()
    shared_sandbox.kill.assert_not_called()


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_run_without_io_trace_success(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test _run_without_io_trace returns correct output structure."""
    mock_get_tracing_span.return_value = None
    mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

    inputs = PythonCodeRunnerToolInputs(python_code="print('Hello, World!')")
    result = await python_code_runner_tool._run_without_io_trace(inputs, {})

    assert isinstance(result, PythonCodeRunnerToolOutputs)
    assert "execution_result" in result.artifacts
    execution_data = json.loads(result.output)
    assert execution_data["error"] is None
    assert execution_data["stdout"] == ["Hello, World!"]
    mock_sandbox.kill.assert_called_once()


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_run_without_io_trace_no_images_in_artifacts(
    mock_get_tracing_span, mock_sandbox_class, python_code_runner_tool, mock_sandbox
):
    """Test that images key is absent from artifacts when no images are generated."""
    mock_get_tracing_span.return_value = None
    mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

    inputs = PythonCodeRunnerToolInputs(python_code="x = 1 + 1")
    result = await python_code_runner_tool._run_without_io_trace(inputs, {})

    assert isinstance(result, PythonCodeRunnerToolOutputs)
    assert "images" not in result.artifacts
    assert "image(s) generated" not in result.output
