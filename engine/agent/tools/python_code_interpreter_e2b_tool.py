import logging
import json
from typing import Any, Optional

from e2b_code_interpreter import Sandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import (
    Agent,
    ChatMessage,
    AgentPayload,
    ToolDescription,
)
from engine.trace.trace_manager import TraceManager
from settings import settings


LOGGER = logging.getLogger(__name__)

E2B_PYTHONCODE_INTERPRETER_TOOL_DESCRIPTION = ToolDescription(
    name="python_code_interpreter",
    description=(
        "Execute Python code in a secure sandbox environment. "
        "Returns the execution result including stdout, stderr, and any generated files."
    ),
    tool_properties={
        "python_code": {
            "type": "string",
            "description": "The Python code to execute in the sandbox.",
        },
    },
    required_tool_properties=["python_code"],
)


class PythonCodeInterpreterE2BTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_instance_name: str,
        tool_description: ToolDescription = E2B_PYTHONCODE_INTERPRETER_TOOL_DESCRIPTION,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self.trace_manager = trace_manager
        self.e2b_api_key = settings.E2B_API_KEY
        self.sandbox_timeout = timeout

    def execute_python_code(self, python_code: str, shared_sandbox: Optional[Sandbox] = None) -> dict:
        """Execute Python code in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")
        sandbox = shared_sandbox if shared_sandbox else Sandbox(api_key=self.e2b_api_key)
        try:
            execution = sandbox.run_code(python_code, timeout=self.sandbox_timeout)
            if not shared_sandbox:
                sandbox.kill()
        except Exception as e:
            LOGGER.error(f"E2B sandbox execution failed: {str(e)}")
            raise e
        return execution.to_json()

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        **kwargs: Any,
    ) -> AgentPayload:
        span = get_current_span()
        trace_input = str(kwargs["python_code"])
        span.set_attributes(
            {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
            }
        )

        execution_result = self.execute_python_code(**kwargs)
        content = json.dumps(execution_result, indent=2)

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts={"execution_result": execution_result},
            is_final=False,
        )
