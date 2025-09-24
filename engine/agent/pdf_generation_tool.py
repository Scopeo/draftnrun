import logging
from datetime import datetime
from typing import Any


from openinference.semconv.trace import OpenInferenceSpanKindValues
import markdown2
from weasyprint import HTML, CSS
from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, AgentPayload, ToolDescription, ComponentAttributes
from engine.temps_folder_utils import get_output_dir
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION = ToolDescription(
    name="Markdown_to_PDF_Tool",
    description="A PDF generation tool that converts markdown text to PDF files.",
    tool_properties={
        "markdown_content": {
            "type": "string",
            "description": (
                "The markdown text to convert to PDF. \n"
                "Insert the image into the markdown in src format. It is recommended to limit the size of "
                'images with a style like this: style="width:80%; max-width:100%; height:auto;"'
            ),
        }
    },
    required_tool_properties=["markdown_content"],
)

DEFAULT_CSS_FORMATTING = """
    @page { size: A4; margin: 18mm; }
    table { border-collapse: collapse; width: 100%; }
        thead tr { background: #f6f8fa; }
        th, td { border: 1px solid #d0d7de; padding: 6px 8px; vertical-align: top; }
        th { font-weight: 600; }
        /* Alignements éventuels générés par certains parseurs */
        th[style*="text-align:center"], td[style*="text-align:center"] { text-align: center; }
        th[style*="text-align:right"],  td[style*="text-align:right"]  { text-align: right; }
        * {font-family: Arial, Helvetica, sans-serif;}
        body {font-size: 12px;line-height: 1.45;color: #111;}
        /* Style des renvois [2] en texte */
        sup a[rel="footnote"] { text-decoration: none; }
        sup a[rel="footnote"]::before { content: "["; }
        sup a[rel="footnote"]::after  { content: "]"; }

        div.footnotes { font-size: 10pt; }
        div.footnotes hr { border: none; border-top: 1px solid #bbb; margin: 10px 0; }

        h1, h2, h3 {
            page-break-after: avoid;   /* évite de couper juste après un titre */
            }

            p {
            orphans: 3;
            widows: 3;                 /* évite les lignes seules en haut/bas de page */
            }

            .page-break {
            page-break-before: always;
            break-before: page;
            }

            /* Liens toujours bleus */
            a, a:visited, a:hover, a:active {
            color: #0645AD;       /* bleu standard */
            text-decoration: underline;
            }"""


class PDFGenerationTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        css_formatting: str = DEFAULT_CSS_FORMATTING,
        tool_description: ToolDescription = DEFAULT_PDF_GENERATION_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.css_formatting = css_formatting

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

        output_dir = get_output_dir()

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"document_{timestamp}.pdf"

        html = markdown2.markdown(
            markdown_content,
            extras=[
                "tables",
                "fenced-code-blocks",
                "strike",
                "footnotes",
                "task_list",
                "header-ids",
                "cuddled-lists",
                "toc",
            ],
        )
        css = CSS(string=self.css_formatting)

        # Create HTML object and ensure proper cleanup
        html_obj = HTML(string=html, base_url=str(output_dir))
        try:
            html_obj.write_pdf(str(output_dir / filename), stylesheets=[css])
        finally:
            # Ensure any HTTP connections are properly closed
            if hasattr(html_obj, "_url_fetcher") and hasattr(html_obj._url_fetcher, "session"):
                try:
                    html_obj._url_fetcher.session.close()
                except Exception:
                    pass

        success_msg = f"PDF generated successfully: {filename}"
        LOGGER.info(success_msg)

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=success_msg)],
            artifacts={"pdf_filename": str(filename)},
            is_final=True,
        )
