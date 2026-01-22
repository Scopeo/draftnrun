import json
import logging
from typing import Any, Optional, Type

from e2b_code_interpreter import AsyncSandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, ConfigDict, Field

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION = ToolDescription(
    name="terminal_command",
    description=(
        "Execute terminal commands in a secure sandbox environment. "
        "Returns the command output including stdout, stderr, and exit code."
    ),
    tool_properties={
        "command": {
            "type": "string",
            "description": "The terminal command to execute in the sandbox.",
        },
    },
    required_tool_properties=["command"],
)


class TerminalCommandRunnerToolInputs(BaseModel):
    command: str = Field(
        default="",
        description="The command to run on the terminal",
    )
    shared_sandbox: Optional[AsyncSandbox] = Field(
        default=None,
        description="The sandbox to use for code execution",
    )
    model_config = ConfigDict(
        extra="allow", arbitrary_types_allowed=True
    )  # For backward compatibility and AsyncSandbox support


class TerminalCommandRunnerToolOutputs(BaseModel):
    output: str = Field(description="The result of the executed command on the terminal.")
    execution_result: dict[str, Any] = Field(description="The full execution result from the sandbox.")


class TerminalCommandRunner(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return TerminalCommandRunnerToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return TerminalCommandRunnerToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "command", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.e2b_api_key = settings.E2B_API_KEY
        self.command_timeout = timeout

    async def execute_terminal_command(self, command: str, shared_sandbox: Optional[AsyncSandbox] = None) -> dict:
        """Execute terminal command in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")

        sandbox = shared_sandbox if shared_sandbox else await AsyncSandbox.create(api_key=self.e2b_api_key)
        try:
            # Use the sandbox's terminal capabilities
            execution = await sandbox.commands.run(command, timeout=self.command_timeout)

            result = {
                "stdout": execution.stdout,
                "stderr": execution.stderr,
                "exit_code": execution.exit_code,
                "command": command,
            }
        except Exception as e:
            LOGGER.error(f"E2B sandbox command execution failed: {str(e)}")
            result = {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "command": command,
                "error": str(e),
            }
        finally:
            if not shared_sandbox:
                await sandbox.kill()

        return result

    async def _run_without_io_trace(
        self,
        inputs: TerminalCommandRunnerToolInputs,
        ctx: dict,
    ) -> TerminalCommandRunnerToolOutputs:
        span = get_current_span()
        command = inputs.command
        shared_sandbox = inputs.shared_sandbox
        trace_input = command
        span.set_attributes({
            SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
            SpanAttributes.INPUT_VALUE: trace_input,
        })

        execution_result_dict = await self.execute_terminal_command(command=command, shared_sandbox=shared_sandbox)
        content = json.dumps(execution_result_dict, indent=2)

        return TerminalCommandRunnerToolOutputs(output=content, execution_result=execution_result_dict)
