import logging

from llama_cloud_services import LlamaParse

LOGGER = logging.getLogger(__name__)


async def _parse_document_with_llamaparse(
    file_input: str,
    llamaparse_api_key: str,
    split_by_page: bool = False,
) -> list[tuple[str, int]] | str:
    parser = LlamaParse(api_key=llamaparse_api_key, parse_mode="parse_document_with_agent", result_type="markdown")
    result = await parser.aparse(file_input)
    try:
        if split_by_page:
            markdown_documents = result.get_markdown_documents(split_by_page=True)
            return [(doc.text, doc.metadata.get("page_number")) for doc in markdown_documents]
        else:
            markdown_documents = result.get_markdown_documents()
            return markdown_documents[0].text
    except Exception as e:
        LOGGER.error(f"Error parsing document {file_input}: {e}", exc_info=True)
        return ""
