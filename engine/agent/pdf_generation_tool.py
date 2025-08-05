import logging
from datetime import datetime
from pathlib import Path
from typing import Any


from openinference.semconv.trace import OpenInferenceSpanKindValues
import markdown2
from weasyprint import HTML
from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, AgentPayload, ToolDescription, ComponentAttributes
from engine.trace.trace_manager import TraceManager
from engine.trace.span_context import get_tracing_span

LOGGER = logging.getLogger(__name__)

DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION = ToolDescription(
    name="Markdown_to_PDF_Tool",
    description=("A PDF generation tool that converts markdown text to PDF files."),
    tool_properties={
        "markdown_content": {
            "type": "string",
            "description": "The markdown text to convert to PDF",
        }
    },
    required_tool_properties=["markdown_content"],
)


class PDFGenerationTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION,
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

        if not markdown_content:
            error_msg = "No markdown content provided"
            LOGGER.error(error_msg)
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=error_msg)],
                error=error_msg,
                is_final=True,
            )

        params = get_tracing_span()
        if not params.uuid_for_temp_folder:
            raise ValueError("UUID for temp folder is not set")

        output_dir = Path(params.uuid_for_temp_folder)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"document_{timestamp}.pdf"

        html = markdown2.markdown(markdown_content)
        HTML(string=html).write_pdf(str(filename))

        success_msg = f"PDF generated successfully: {filename}"
        LOGGER.info(success_msg)

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=success_msg)],
            artifacts={"pdf_filename": str(filename)},
            is_final=True,
        )
