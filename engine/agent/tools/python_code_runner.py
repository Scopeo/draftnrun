import base64
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from PIL import Image
from io import BytesIO
import os
import hashlib

from e2b import EntryInfo
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
VALID_E2B_FILE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".csv", ".md"}

SUPPORTED_PIXEL_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


@dataclass
class SandboxFileRecord:
    """Represents a file in the E2B sandbox."""

    name: str
    remote_path: str
    local_path: Path
    fp_pixel: Optional[str] = None


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
        return Path(path).suffix.lower() in VALID_E2B_FILE_EXTS

    def _save_images_from_results(self, execution_result: dict, files_records: list[dict]) -> list[str]:
        """Extract all images from E2B execution results if any exist."""
        results = execution_result.get("results", [])
        output_dir = get_output_dir()
        images_paths: list[str] = []

        file_fp = [r["fp_pixel"] for r in files_records if r.get("fp_pixel")]

        for result in results:
            for image_format in ["png", "jpg", "jpeg", "svg", "gif", "webp"]:
                image_data = getattr(result, image_format, None)
                if image_data:
                    fp = fp_pixel_from_base64(image_data)
                    if fp in file_fp:
                        LOGGER.info("Skipping image already saved as file")
                        continue
                    uuid = uuid4().hex
                    image_name = f"image_{uuid}.{image_format}"
                    image_path = output_dir / image_name
                    with open(image_path, "wb") as img_file:
                        img_file.write(base64.b64decode(image_data))
                    images_paths.append(str(image_name))

        return images_paths

    async def _collect_new_files(
        self, sandbox: AsyncSandbox, before_map: dict[str, EntryInfo], records: list[SandboxFileRecord]
    ) -> list[SandboxFileRecord]:
        """Collect new files created in the sandbox, save them locally, and update records."""
        after = await sandbox.files.list(".", depth=1)
        after_map = {e.path: e for e in after}
        new_entries = [
            after_map[p] for p in (set(after_map.keys()) - set(before_map.keys())) if self._is_file_to_save(p)
        ]

        output_dir = get_output_dir()

        for entry in new_entries:
            b = await sandbox.files.read(entry.path, format="bytes")
            local_path = output_dir / entry.name
            with open(local_path, "wb") as f:
                f.write(b)

            fp_pixel = None
            if os.path.splitext(entry.name)[1].lower() in SUPPORTED_PIXEL_EXTS:
                try:
                    fp_pixel = fp_pixel_from_bytes(b)
                except Exception as e:
                    LOGGER.error(f"Failed to get pixel hash for {entry.name}: {str(e)}")

            record = SandboxFileRecord(
                name=entry.name,
                remote_path=entry.path,
                local_path=local_path,
                fp_pixel=fp_pixel,
            )
            records.append(record)

        LOGGER.info(f"E2B execution completed with {len(new_entries)} new files created.")
        return records

    async def execute_python_code(
        self, python_code: str, shared_sandbox: Optional[AsyncSandbox] = None
    ) -> tuple[dict, list[SandboxFileRecord]]:
        """Execute Python code in E2B sandbox and return the result."""
        if not self.e2b_api_key:
            raise ValueError("E2B API key not configured")

        sandbox = shared_sandbox
        if not sandbox:
            sandbox = await AsyncSandbox.create(api_key=self.e2b_api_key)
        records: list[SandboxFileRecord] = []
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
            records = await self._collect_new_files(sandbox, before_map, records)
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

        images_paths = self._save_images_from_results(execution_result_dict, records)
        artifacts = {"execution_result": execution_result_dict}
        if images_paths:
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
