import pymupdf4llm
import tempfile
import urllib.request
import urllib.parse
import os
from pathlib import Path
from typing import Any

from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ChatMessage, ToolDescription, ComponentAttributes
from engine.trace.trace_manager import TraceManager
from engine.temps_folder_utils import get_output_dir


DEFAULT_PDF_PARSING_TOOL_DESCRIPTION = ToolDescription(
    name="PDF Parsing Tool",
    description="Parse PDF files and convert them to markdown text for further processing in workflows. Accepts either local file paths or URLs.",
    tool_properties={
        "file_input": {
            "type": "string",
            "description": "Either a local file path or URL to the PDF file to parse.",
        }
    },
    required_tool_properties=["file_input"],
)


class PDFParsingTool(Agent):
    def __init__(
        self, trace_manager: TraceManager, component_attributes: ComponentAttributes, tool_description: ToolDescription
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs: Any) -> AgentPayload:
        file_input = kwargs.get("file_input")
        if not file_input:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="No file input provided")])

        temp_file_path = None
        try:
            if self.is_url(file_input):
                file_path = await self._download_file_from_url(file_input)
                temp_file_path = file_path
            else:
                file_path = Path(file_input)
                if not file_path.is_absolute():
                    file_path = get_output_dir() / file_input

                if not file_path.exists():
                    return AgentPayload(
                        messages=[ChatMessage(role="assistant", content=f"File {file_input} not found")]
                    )

            md_text = pymupdf4llm.to_markdown(file_path)

            return AgentPayload(messages=[ChatMessage(role="assistant", content=md_text)])

        except Exception as e:
            return AgentPayload(messages=[ChatMessage(role="assistant", content=f"Error parsing PDF: {e}")])
        finally:
            if temp_file_path and temp_file_path.exists():
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass

    @staticmethod
    def is_url(input_string: str) -> bool:
        try:
            result = urllib.parse.urlparse(input_string)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    async def _download_file_from_url(url: str) -> Path:
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_path = Path(temp_file.name)
            temp_file.close()

            urllib.request.urlretrieve(url, temp_path)

            return temp_path
        except Exception as e:
            raise Exception(f"Failed to download file from URL {url}: {e}")
