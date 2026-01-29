import logging
import tempfile
from typing import Any, Optional, Type

from md2docx_python.src.md2docx_python import markdown_to_word
from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import prepare_markdown_output_path
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


class DOCXGenerationToolInputs(BaseModel):
    markdown_content: str = Field(description="The markdown text to convert to DOCX.")
    filename: Optional[str] = Field(description="The desired filename for the generated DOCX file.")


class DOCXGenerationToolOutputs(BaseModel):
    output_message: str = Field(description="The output message to be returned to the user.")
    # TODO: Make simple docx_filename field instead of artifacts dictionary
    artifacts: dict[str, Any] = Field(description="The artifacts to be returned to the user.")


class DOCXGenerationTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return DOCXGenerationToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return DOCXGenerationToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "markdown_content", "output": "output_message"}

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
        inputs: DOCXGenerationToolInputs,
        ctx: dict,
        **kwargs: Any,
    ) -> DOCXGenerationToolOutputs:
        try:
            markdown_content, output_path, filename = prepare_markdown_output_path(
                markdown_content=inputs.markdown_content,
                filename=inputs.filename,
                output_dir_getter=get_output_dir,
                default_extension=".docx",
            )
        except ValueError as ve:
            error_msg = str(ve)
            LOGGER.error(error_msg)
            return DOCXGenerationToolOutputs(
                output_message=error_msg,
                artifacts={},
            )
        except Exception as e:
            error_msg = f"Failed to prepare output path: {e}"
            LOGGER.error(error_msg)
            return DOCXGenerationToolOutputs(
                output_message=error_msg,
                artifacts={},
            )

        # Create a temporary markdown file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp_md:
            tmp_md.write(markdown_content.encode("utf-8"))
            tmp_md_path = tmp_md.name

        try:
            markdown_to_word(tmp_md_path, str(output_path))
            success_msg = f"{filename} file has been generated successfully"
            LOGGER.info(success_msg)

            return DOCXGenerationToolOutputs(
                output_message=success_msg,
                artifacts={"docx_filename": str(filename)},
            )

        except Exception as e:
            error_msg = f"Failed to generate DOCX: {str(e)}"
            LOGGER.error(error_msg)
            return DOCXGenerationToolOutputs(
                output_message=error_msg,
                artifacts={},
            )
