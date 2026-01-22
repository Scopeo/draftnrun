import logging

from llama_cloud_services import LlamaParse

LOGGER = logging.getLogger(__name__)


async def _parse_document_with_llamaparse(
    file_input: str,
    llamaparse_api_key: str,
) -> str:
    parser = LlamaParse(api_key=llamaparse_api_key, parse_mode="parse_document_with_agent", result_type="markdown")
    result = await parser.aparse(file_input)
    markdown_documents = result.get_markdown_documents()
    if not markdown_documents:
        LOGGER.warning(f"No markdown documents found for file {file_input}")
        return ""
    return markdown_documents[0].text
