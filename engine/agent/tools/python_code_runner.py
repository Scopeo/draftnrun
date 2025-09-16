import base64
from datetime import datetime
import logging
from typing import Any, Optional
from PIL import Image
from io import BytesIO
import os, hashlib

from e2b_code_interpreter import AsyncSandbox
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import (
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
)
from engine.temps_folder_utils import get_output_dir
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
VALID_FILE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".csv", ".md"}

ALLOWED_EXTS_PIXEL = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


def fp_pixel_from_base64(b64_str: str) -> str:
    data = base64.b64decode(b64_str)
    return fp_pixel_from_bytes(data)


def fp_pixel_from_bytes(data: bytes) -> str:
    with Image.open(BytesIO(data)) as im:
        im.load()
        im = im.convert("RGBA")
        payload = (im.mode + str(im.size)).encode() + im.tobytes()
    return hashlib.sha256(payload).hexdigest()


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

    @staticmethod
    def _is_file_to_save(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in VALID_FILE_EXTS

    def _extract_images_from_results(self, execution_result: dict, files_records: list[dict]) -> list[str]:
        """Extract all images from E2B execution results if any exist."""
        images = []
        results = execution_result.get("results", [])

        file_fp = [r["fp_pixel"] for r in files_records if r.get("fp_pixel")]

        for result in results:
            for image_format in ["png", "jpg", "jpeg", "svg", "gif", "webp"]:
                image_data = getattr(result, image_format, None)
                if image_data:
                    fp = fp_pixel_from_base64(image_data)
                    if fp in file_fp:
                        LOGGER.info(f"Skipping image already saved as file")
                        continue
                    images.append(image_data)

        return images

    async def execute_python_code(self, python_code: str, shared_sandbox: Optional[AsyncSandbox] = None) -> dict:
        """Execute Python code in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")

        sandbox = shared_sandbox
        if not sandbox:
            sandbox = await AsyncSandbox.create(api_key=self.e2b_api_key)
        records = []
        try:
            before = await sandbox.files.list(".", depth=1)
            before_map = {e.path: e for e in before}

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
            after = await sandbox.files.list(".", depth=1)
            after_map = {e.path: e for e in after}
            new_entries = [
                after_map[p] for p in (set(after_map.keys()) - set(before_map.keys())) if self._is_file_to_save(p)
            ]
            for entry in new_entries:
                b = await sandbox.files.read(entry.path, format="bytes")
                local_path = get_output_dir() / entry.name
                with open(local_path, "wb") as f:
                    f.write(b)
                record = {
                    "name": entry.name,
                    "remote_path": entry.path,
                    "local_path": entry.name,
                }
                if os.path.splitext(entry.name)[1].lower() in ALLOWED_EXTS_PIXEL:
                    try:
                        fp = fp_pixel_from_bytes(b)
                        record["fp_pixel"] = fp
                    except Exception as e:
                        LOGGER.error(f"Failed to get pixel hash for {entry.name}: {str(e)}")

                records.append(record)
            LOGGER.info(f"E2B execution completed with {len(new_entries)} new files created.")
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
        return result, records

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

        execution_result_dict, records = await self.execute_python_code(
            python_code=python_code, shared_sandbox=shared_sandbox
        )
        content = serialize_to_json(execution_result_dict)

        images = self._extract_images_from_results(execution_result_dict, records)
        artifacts = {"execution_result": execution_result_dict}
        if images:
            output_dir = get_output_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            images_paths = []
            for i, image in enumerate(images):
                image_name = f"image_{timestamp}_{i + 1}.png"
                image_path = output_dir / image_name
                with open(image_path, "wb") as img_file:
                    img_file.write(image.encode("utf-8"))
                images_paths.append(str(image_name))
            artifacts["images"] = images_paths
            content += (
                f"\n\n[{len(images_paths)} image(s) generated and included in artifacts : {', '.join(images_paths)}]"
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts=artifacts,
            error=execution_result_dict.get("error", None),
            is_final=False,
        )
