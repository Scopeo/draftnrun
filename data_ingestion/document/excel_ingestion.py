import logging
import uuid
from typing import Callable

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.llamaparser_ingestion import _parse_document_with_llamaparse
from data_ingestion.utils import content_as_temporary_file_path

LOGGER = logging.getLogger(__name__)


async def create_chunks_from_excel_file_with_llamaparse(
    document: FileDocument,
    get_file_content_func: Callable[[str], bytes],
    llamaparse_api_key: str,
    **kwargs,
) -> list[FileChunk]:
    try:
        result_chunks = []
        content_to_process = get_file_content_func(document.id)
        with content_as_temporary_file_path(content_to_process, suffix=".xlsx") as file_path:
            try:
                markdown_documents = await _parse_document_with_llamaparse(
                    file_path, llamaparse_api_key, split_by_page=True
                )
                for i, (markdown_content, page_number) in enumerate(markdown_documents):
                    result_chunks.append(
                        FileChunk(
                            chunk_id=str(uuid.uuid4()),
                            order=i,
                            file_id=document.id,
                            content=markdown_content,
                            last_edited_ts=document.last_edited_ts,
                            document_title=document.file_name,
                            bounding_boxes=None,
                            url=document.url,
                            metadata={
                                "page_number": page_number,
                                **document.metadata,
                            },
                        )
                    )
            except Exception as e:
                LOGGER.error(f"Error parsing Excel file {document.file_name}: {e}", exc_info=True)
                raise Exception(f"Error parsing Excel file {document.file_name}") from e
    except Exception as e:
        LOGGER.error(f"Error parsing Excel file {document.file_name}: {e}", exc_info=True)
        raise Exception(f"Error parsing Excel file {document.file_name}") from e
    return result_chunks
