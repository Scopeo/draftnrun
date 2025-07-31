import logging
import uuid
from datetime import datetime
from pathlib import Path
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


def delete_pdf_file_if_exists(final_output: AgentPayload | dict) -> None:
    # Convert to dict if it's an AgentPayload object
    if not isinstance(final_output, dict):
        final_output = final_output.__dict__
    artifacts = final_output.get("artifacts", {})
    if artifacts:
        pdf_filename = artifacts.get("pdf_filename", None)
        if pdf_filename:
            pdf_path = Path(pdf_filename)
            if pdf_path.exists() and pdf_path.is_file():
                # Delete the PDF file
                pdf_path.unlink()
                LOGGER.info(f"Deleted PDF file: {pdf_path}")

                # Check if the parent directory is empty and remove it if so
                parent_dir = pdf_path.parent
                if parent_dir.exists() and parent_dir.is_dir():
                    try:
                        # Check if directory is empty (no files or subdirectories)
                        if not any(parent_dir.iterdir()):
                            parent_dir.rmdir()
                            LOGGER.info(f"Deleted empty directory: {parent_dir}")
                    except OSError as e:
                        LOGGER.warning(f"Could not remove directory {parent_dir}: {e}")


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

        uuid_suffix = str(uuid.uuid4())
        output_dir = Path("temp") / f"{uuid_suffix}"
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
