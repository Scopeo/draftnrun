import logging
from pathlib import Path
from typing import Callable, Optional

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.llamaparser_ingestion import _parse_document_with_llamaparse
from data_ingestion.document.markdown_ingestion import chunk_markdown
from data_ingestion.utils import content_as_temporary_file_path

LOGGER = logging.getLogger(__name__)

EXCEL_CHUNK_SIZE = 1024
EXCEL_CHUNK_OVERLAP = 50


async def create_chunks_from_excel_file_with_llamaparse(
    document: FileDocument,
    get_file_content_func: Callable[[str], bytes],
    llamaparse_api_key: str,
    chunk_size: Optional[int] = EXCEL_CHUNK_SIZE,
    chunk_overlap: int = EXCEL_CHUNK_OVERLAP,
    **kwargs,
) -> list[FileChunk]:
    try:
        content_to_process = get_file_content_func(document.id)
        suffix = Path(document.file_name).suffix or document.type.value
        with content_as_temporary_file_path(content_to_process, suffix=suffix) as file_path:
            try:
                markdown_documents = await _parse_document_with_llamaparse(
                    file_path, llamaparse_api_key, split_by_page=True
                )
                all_markdown = "\n\n".join(content for content, _ in markdown_documents)
                result_chunks = chunk_markdown(
                    document_to_process=document,
                    content=all_markdown,
                    chunk_size=chunk_size or EXCEL_CHUNK_SIZE,
                    chunk_overlap=chunk_overlap,
                )
            except Exception as e:
                LOGGER.error(f"Error parsing Excel file {document.file_name}: {e}", exc_info=True)
                raise Exception(f"Error parsing Excel file {document.file_name}") from e
    except Exception as e:
        LOGGER.error(f"Error parsing Excel file {document.file_name}: {e}", exc_info=True)
        raise Exception(f"Error parsing Excel file {document.file_name}") from e
    return result_chunks
