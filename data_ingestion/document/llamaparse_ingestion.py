import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

from llama_cloud_services import LlamaParse

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.markdown_ingestion import chunk_markdown
from settings import settings

LOGGER = logging.getLogger(__name__)


async def _parse_pdf_with_llamaparse(file_input: str) -> str:
    parser = LlamaParse(
        api_key=settings.LLAMACLOUD_API_KEY, parse_mode="parse_document_with_agent", result_type="markdown"
    )
    result = await parser.aparse(file_input)
    markdown_documents = result.get_markdown_documents()
    return markdown_documents[0].text


async def create_chunks_from_document_with_llamaparse(
    document: FileDocument,
    get_file_content: Callable[[str], bytes | str],
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
    **kwargs,
) -> list[FileChunk]:
    try:
        content_to_process = get_file_content(document.id)
        if isinstance(content_to_process, bytes):
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_path = Path(temp_file.name)
            temp_file.write(content_to_process)
            temp_file.close()
            try:
                markdown_text = await _parse_pdf_with_llamaparse(str(temp_path))
            except Exception as e:
                LOGGER.error(f"Error parsing PDF {document.file_name} with llamaparser", exc_info=True)
                raise e
            finally:
                if temp_path.exists():
                    os.unlink(temp_path)
        else:
            markdown_text = await _parse_pdf_with_llamaparse(content_to_process)
        return chunk_markdown(
            document_to_process=document,
            content=markdown_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except Exception as e:
        LOGGER.error(f"Error processing PDF {document.file_name} with llamaparser", exc_info=True)
        raise e
