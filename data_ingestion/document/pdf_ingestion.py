import logging
from typing import Callable, Optional

import pymupdf4llm
from llama_cloud_services import LlamaParse

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.markdown_ingestion import chunk_markdown
from data_ingestion.utils import get_file_path_from_content

LOGGER = logging.getLogger(__name__)


async def _parse_pdf_without_llm(file_input: str) -> str:
    md_text = pymupdf4llm.to_markdown(file_input)
    return md_text


async def _parse_pdf_with_llamaparse(
    file_input: str,
    llamaparse_api_key: str,
) -> str:
    parser = LlamaParse(api_key=llamaparse_api_key, parse_mode="parse_document_with_agent", result_type="markdown")
    result = await parser.aparse(file_input)
    markdown_documents = result.get_markdown_documents()
    return markdown_documents[0].text


async def create_chunks_from_pdf_document(
    document: FileDocument,
    get_file_content: Callable[[str], bytes | str],
    pdf_parser: Callable[[str], str],
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
    **kwargs,
) -> list[FileChunk]:
    try:
        content_to_process = get_file_content(document.id)
        with get_file_path_from_content(content_to_process, suffix=".pdf") as file_path:
            try:
                markdown_text = await pdf_parser(file_path)
            except Exception as e:
                LOGGER.error(
                    f"Error parsing PDF {document.file_name}: {e}",
                    exc_info=True,
                )
                raise Exception(f"Error parsing PDF {document.file_name}") from e
        return chunk_markdown(
            document_to_process=document,
            content=markdown_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except Exception as e:
        LOGGER.error(f"Error processing PDF {document.file_name}: {e}", exc_info=True)
        raise Exception(f"Error processing PDF {document.file_name}") from e
