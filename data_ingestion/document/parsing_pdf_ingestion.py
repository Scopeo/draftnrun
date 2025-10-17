import logging
import tempfile
import os
from pathlib import Path
from typing import Callable, Optional

import pymupdf4llm

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.markdown_ingestion import chunk_markdown


LOGGER = logging.getLogger(__name__)


def _parse_pdf_without_llm(file_input: str) -> str:
    md_text = pymupdf4llm.to_markdown(file_input)
    return md_text


async def create_chunks_from_document_without_llm(
    document: FileDocument,
    get_file_content: Callable[[FileDocument], str],
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
                markdown_text = _parse_pdf_without_llm(str(temp_path))
            except Exception as e:
                LOGGER.error(f"Error parsing PDF {document.file_name} without LLM: {e}", exc_info=True)
                raise Exception(f"Error parsing PDF {document.file_name} without LLM") from e
            finally:
                if temp_path.exists():
                    os.unlink(temp_path)
        else:
            markdown_text = _parse_pdf_without_llm(content_to_process)
        return chunk_markdown(
            document_to_process=document,
            content=markdown_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    except Exception as e:
        LOGGER.error(f"Error processing PDF {document.file_name} without LLM: {e}", exc_info=True)
        raise Exception(f"Error processing PDF {document.file_name} without LLM") from e
