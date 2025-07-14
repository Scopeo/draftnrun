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
        "Returns the execution result including stdout, stderr, generated files, and images."
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

    def _extract_images_from_results(self, execution_result: dict) -> list[str]:
        """Extract all images from E2B execution results if any exist."""
        images = []
        results = execution_result.get("results", [])

        for result in results:
            if isinstance(result, dict):
                # Check for image properties directly on result objects
                # E2B automatically detects matplotlib plots and adds them as base64 encoded images
                for image_format in ["png", "jpg", "jpeg", "svg"]:
                    if image_format in result and result[image_format]:
                        # The image is already base64 encoded according to E2B docs
                        images.append(result[image_format])

        return images

    def execute_python_code(self, python_code: str, shared_sandbox: Optional[Sandbox] = None) -> dict:
        """Execute Python code in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")
        sandbox = shared_sandbox if shared_sandbox else Sandbox(api_key=self.e2b_api_key)
        try:
            execution = sandbox.run_code(python_code)
            result = {
                "results": str(execution.results),
                "stdout": str(execution.logs.stdout),
                "stderr": str(execution.logs.stderr),
                "error": str(execution.error),
            }
        except Exception as e:
            LOGGER.error(f"E2B sandbox execution failed: {str(e)}")
            result = {
                "results": [],
                "stdout": [],
                "stderr": [str(e)],
                "error": str(e),
            }
        finally:
            if not shared_sandbox:
                sandbox.kill()
        return result

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

        # Extract only the parameters that execute_python_code accepts
        python_code = kwargs["python_code"]
        shared_sandbox = kwargs.get("shared_sandbox")
        
        execution_result_dict = self.execute_python_code(
            python_code=python_code, 
            shared_sandbox=shared_sandbox
        )
        content = json.dumps(execution_result_dict, indent=2)

        images = self._extract_images_from_results(execution_result_dict)
        artifacts = {"execution_result": execution_result_dict}
        if images:
            artifacts["images"] = images
            content += f"\n\n[{len(images)} image(s) generated and included in artifacts]"

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts=artifacts,
            is_final=False,
        )
