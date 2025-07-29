import logging
from typing import Any


from openinference.semconv.trace import OpenInferenceSpanKindValues
import markdown2
from weasyprint import HTML

from engine.agent.agent import Agent, ComponentAttributes, ToolDescription, AgentPayload, ChatMessage
from engine.trace.trace_manager import TraceManager

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

    async def _run_without_trace(
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

        filename = "generated_document.pdf"

        try:
            # Convert markdown to HTML
            print(markdown_content)
            html = markdown2.markdown(markdown_content)

            # Generate PDF from HTML
            HTML(string=html).write_pdf(filename)

            success_msg = f"PDF generated successfully: {filename}"
            LOGGER.info(success_msg)

            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=success_msg)],
                artifacts={"pdf_filename": filename},
                is_final=True,
            )

        except Exception as e:
            error_msg = f"Failed to generate PDF: {str(e)}"
            LOGGER.error(error_msg)

            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=error_msg)],
                error=error_msg,
                is_final=True,
            )
