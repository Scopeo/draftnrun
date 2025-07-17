import logging
from typing import Any, Optional

from e2b_code_interpreter import AsyncSandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.data_structures import (
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
)
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager
from settings import settings


LOGGER = logging.getLogger(__name__)

PYTHON_CODE_RUNNER_TOOL_DESCRIPTION = ToolDescription(
    name="python_code_runner",
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


class PythonCodeRunner(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = PYTHON_CODE_RUNNER_TOOL_DESCRIPTION,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.e2b_api_key = settings.E2B_API_KEY
        self.sandbox_timeout = timeout

    def _extract_images_from_results(self, execution_result: dict) -> list[str]:
        """Extract all images from E2B execution results if any exist."""
        images = []
        results = execution_result.get("results", [])

        for result in results:
            for image_format in ["png", "jpg", "jpeg", "svg", "gif", "webp"]:
                image_data = getattr(result, image_format, None)
                if image_data:
                    images.append(image_data)

        return images

    async def execute_python_code(self, python_code: str, shared_sandbox: Optional[AsyncSandbox] = None) -> dict:
        """Execute Python code in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")

        sandbox = shared_sandbox
        if not sandbox:
            sandbox = await AsyncSandbox.create(api_key=self.e2b_api_key)
        try:
            LOGGER.info("Executing Python code in E2B sandbox")
            execution = await sandbox.run_code(code=python_code, timeout=self.sandbox_timeout)
            result = {
                "results": execution.results if hasattr(execution, "results") else [],
                "stdout": (
                    execution.logs.stdout if hasattr(execution, "logs") and hasattr(execution.logs, "stdout") else []
                ),
                "stderr": (
                    execution.logs.stderr if hasattr(execution, "logs") and hasattr(execution.logs, "stderr") else []
                ),
                "error": str(execution.error) if hasattr(execution, "error") and execution.error else None,
                "execution_count": getattr(execution, "execution_count", 1),
            }
        except Exception as e:
            LOGGER.error(f"E2B sandbox execution failed: {str(e)}")
            result = {
                "results": [],
                "stdout": [],
                "stderr": [],
                "error": str(e),
            }
        finally:
            if not shared_sandbox:
                await sandbox.kill()
        return result

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        **kwargs: Any,
    ) -> AgentPayload:
        span = get_current_span()
        trace_input = str(kwargs.get("python_code", ""))
        span.set_attributes(
            {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
            }
        )

        python_code = kwargs["python_code"]
        shared_sandbox = kwargs.get("shared_sandbox")

        execution_result_dict = await self.execute_python_code(python_code=python_code, shared_sandbox=shared_sandbox)
        content = serialize_to_json(execution_result_dict)

        images = self._extract_images_from_results(execution_result_dict)
        artifacts = {"execution_result": execution_result_dict}
        if images:
            artifacts["images"] = images
            content += f"\n\n[{len(images)} image(s) generated and included in artifacts]"

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts=artifacts,
            error=execution_result_dict.get("error", None),
            is_final=False,
        )
