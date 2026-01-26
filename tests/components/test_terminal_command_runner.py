import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from engine.components.tools.terminal_command_runner import (
    TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION,
    TerminalCommandRunner,
    TerminalCommandRunnerToolInputs,
    TerminalCommandRunnerToolOutputs,
)
from tests.mocks.trace_manager import MockTraceManager


@pytest.fixture
def mock_e2b_api_key():
    with patch("engine.components.tools.terminal_command_runner.settings") as mock_settings:
        mock_settings.E2B_API_KEY = "test_api_key"
        yield


@pytest.fixture
def terminal_command_tool(mock_e2b_api_key):
    from engine.components.component import ComponentAttributes

    trace_manager = MockTraceManager(project_name="test_project")
    return TerminalCommandRunner(
        trace_manager=trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_terminal_command_tool"),
        timeout=30,
    )


@pytest.fixture
def mock_sandbox():
    mock_sandbox = AsyncMock()
    mock_execution = Mock()
    mock_execution.stdout = "Hello World\n"
    mock_execution.stderr = ""
    mock_execution.exit_code = 0
    mock_sandbox.commands.run.return_value = mock_execution
    mock_sandbox.kill.return_value = None
    return mock_sandbox


class TestTerminalCommandE2BTool:
    def test_tool_description(self):
        """Test that the tool description is correctly defined."""
        assert TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.name == "terminal_command"
        assert "terminal command" in TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.description.lower()
        assert "command" in TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.tool_properties
        assert TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.required_tool_properties == ["command"]

    def test_initialization(self, terminal_command_tool):
        """Test that the tool initializes correctly."""
        assert terminal_command_tool.component_attributes.component_instance_name == "test_terminal_command_tool"
        assert terminal_command_tool.command_timeout == 30
        assert terminal_command_tool.e2b_api_key == "test_api_key"

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_execute_terminal_command_success(self, mock_sandbox_class, terminal_command_tool, mock_sandbox):
        """Test successful command execution."""
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        result = await terminal_command_tool.execute_terminal_command("echo 'Hello World'")

        assert result["stdout"] == "Hello World\n"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0
        assert result["command"] == "echo 'Hello World'"
        assert "error" not in result

        mock_sandbox.commands.run.assert_called_once_with("echo 'Hello World'", timeout=30)
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_execute_terminal_command_with_shared_sandbox(
        self, mock_sandbox_class, terminal_command_tool, mock_sandbox
    ):
        """Test command execution with a shared sandbox."""
        shared_sandbox = AsyncMock()
        shared_execution = Mock()
        shared_execution.stdout = "Shared output\n"
        shared_execution.stderr = ""
        shared_execution.exit_code = 0
        shared_sandbox.commands.run.return_value = shared_execution

        result = await terminal_command_tool.execute_terminal_command("ls -la", shared_sandbox=shared_sandbox)

        assert result["stdout"] == "Shared output\n"
        assert result["exit_code"] == 0

        # Should not create a new sandbox or kill the shared one
        mock_sandbox_class.assert_not_called()
        shared_sandbox.kill.assert_not_called()
        shared_sandbox.commands.run.assert_called_once_with("ls -la", timeout=30)

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_execute_terminal_command_error(self, mock_sandbox_class, terminal_command_tool, mock_sandbox):
        """Test command execution with error."""
        mock_sandbox.commands.run.side_effect = Exception("Command failed")
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        result = await terminal_command_tool.execute_terminal_command("invalid_command")

        assert result["stdout"] == ""
        assert result["stderr"] == "Command failed"
        assert result["exit_code"] == -1
        assert result["command"] == "invalid_command"
        assert result["error"] == "Command failed"

        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_execute_terminal_command_no_api_key(self, mock_sandbox_class, terminal_command_tool):
        """Test that ValueError is raised when no API key is configured."""
        terminal_command_tool.e2b_api_key = None

        with pytest.raises(ValueError, match="E2B API key not configured"):
            await terminal_command_tool.execute_terminal_command("echo test")

        mock_sandbox_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_run_without_io_trace_basic(self, mock_sandbox_class, terminal_command_tool, mock_sandbox):
        """Test the basic _run_without_io_trace functionality."""
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        inputs = TerminalCommandRunnerToolInputs(command="pwd")
        result = await terminal_command_tool._run_without_io_trace(inputs, {})

        assert isinstance(result, TerminalCommandRunnerToolOutputs)

        content = json.loads(result.output)
        assert content["stdout"] == "Hello World\n"
        assert content["command"] == "pwd"
        assert content["exit_code"] == 0

        assert "execution_result" in result.artifacts

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_run_without_io_trace_with_error(self, mock_sandbox_class, terminal_command_tool, mock_sandbox):
        """Test _run_without_io_trace with command that produces an error."""
        mock_execution = Mock()
        mock_execution.stdout = ""
        mock_execution.stderr = "command not found"
        mock_execution.exit_code = 127
        mock_sandbox.commands.run.return_value = mock_execution
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        inputs = TerminalCommandRunnerToolInputs(command="invalid_cmd")
        result = await terminal_command_tool._run_without_io_trace(inputs, {})

        assert isinstance(result, TerminalCommandRunnerToolOutputs)

        content = json.loads(result.output)
        assert content["stderr"] == "command not found"
        assert content["exit_code"] == 127
        assert content["command"] == "invalid_cmd"

    @pytest.mark.asyncio
    @patch("engine.components.tools.terminal_command_runner.AsyncSandbox")
    async def test_run_without_io_trace_exception_handling(
        self, mock_sandbox_class, terminal_command_tool, mock_sandbox
    ):
        """Test that exceptions during execution are handled properly."""
        mock_sandbox.commands.run.side_effect = Exception("Sandbox error")
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        inputs = TerminalCommandRunnerToolInputs(command="test_cmd")
        result = await terminal_command_tool._run_without_io_trace(inputs, {})

        assert isinstance(result, TerminalCommandRunnerToolOutputs)

        content = json.loads(result.output)
        assert content["stderr"] == "Sandbox error"
        assert content["exit_code"] == -1
        assert content["error"] == "Sandbox error"

        # Ensure sandbox cleanup happens even on error
        mock_sandbox.kill.assert_called_once()
