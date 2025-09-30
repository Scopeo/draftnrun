import logging
import tempfile
from datetime import datetime
from typing import Any


from openinference.semconv.trace import OpenInferenceSpanKindValues
from md2docx_python.src.md2docx_python import markdown_to_word
from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, AgentPayload, ToolDescription, ComponentAttributes
from engine.temps_folder_utils import get_output_dir
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_DOCX_GENERATION_TOOL_DESCRIPTION = ToolDescription(
    name="Markdown_to_DOCX_Tool",
    description="A DOCX generation tool that converts markdown text to DOCX files.",
    tool_properties={
        "markdown_content": {
            "type": "string",
            "description": ("The markdown text to convert to DOCX."),
        },
        "filename": {
            "type": "string",
            "description": (
                "Optional. The desired filename for the generated DOCX file. If not provided, a default "
                "filename with a timestamp will be used."
            ),
        },
    },
    required_tool_properties=["markdown_content"],
)


class DOCXGenerationTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_DOCX_GENERATION_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        **kwargs: Any,
    ) -> AgentPayload:
        markdown_content = kwargs.get("markdown_content", "")
        filename = kwargs.get("filename", None)

        if not markdown_content:
            error_msg = "No markdown content provided"
            LOGGER.error(error_msg)
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=error_msg)],
                error=error_msg,
                is_final=True,
            )

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"document_{timestamp}.docx"

        output_dir = get_output_dir()

        output_path = output_dir / filename

        # Create a temporary markdown file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp_md:
            tmp_md.write(markdown_content.encode("utf-8"))
            tmp_md_path = tmp_md.name

        try:
            markdown_to_word(tmp_md_path, str(output_path))
            success_msg = f"DOCX generated successfully: {filename}"
            LOGGER.info(success_msg)

            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=success_msg)],
                artifacts={"docx_filename": str(filename)},
                is_final=True,
            )

        except Exception as e:
            error_msg = f"Failed to generate DOCX: {str(e)}"
            LOGGER.error(error_msg)
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=error_msg)],
                error=error_msg,
                is_final=True,
            )
