import json
import logging
from typing import Any, Optional, Type

from e2b_code_interpreter import AsyncSandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, ConfigDict, Field

from ada_backend.database.models import UIComponent
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.span_context import get_tracing_span
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
        json_schema_extra={"ui_component": UIComponent.TEXTAREA},
    )
    shared_sandbox: Optional[AsyncSandbox] = Field(
        default=None,
        description="The sandbox to use for code execution",
        json_schema_extra={"disabled_as_input": True},
    )
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TerminalCommandRunnerToolOutputs(BaseModel):
    output: str = Field(description="The result of the executed command on the terminal.")
    artifacts: dict[str, Any] = Field(
        default_factory=dict, description="Artifacts produced by the terminal code runner."
    )


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

        params = get_tracing_span()

        if params and params.shared_sandbox:
            sandbox = params.shared_sandbox
        elif shared_sandbox:
            sandbox = shared_sandbox
        else:
            sandbox = await AsyncSandbox.create(api_key=self.e2b_api_key)
            if params:
                params.shared_sandbox = sandbox

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
            # Only cleanup if sandbox was passed explicitly (not from context)
            if shared_sandbox and not (params and params.shared_sandbox == sandbox):
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
        span.set_attributes({
            SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
            SpanAttributes.INPUT_VALUE: str(command),
        })

        execution_result_dict = await self.execute_terminal_command(command=command, shared_sandbox=shared_sandbox)
        content = json.dumps(execution_result_dict, indent=2)
        artifacts = {"execution_result": execution_result_dict}

        return TerminalCommandRunnerToolOutputs(output=content, artifacts=artifacts)
