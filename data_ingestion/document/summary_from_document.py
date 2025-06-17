import logging
from typing import Callable

from data_ingestion.document.folder_management.folder_management import FileDocumentType, FileChunk
from engine.llm_services.google_llm_service import GoogleLLMService, TypeFileToUpload

LOGGER = logging.getLogger(__name__)

DEFAULT_PROMPT_TEMPLATE_SUMMARY = """Sum up the attached document and keep the key elements.
Try to keep the meaning of acronyms.
Do not begin your answer by putting 'Here is the sum up of ...' or something similar.
Be concise. Try to do a short summary of maximum 4-5 sentences.
Answer in French if the text is in French, and English otherwise.
"""

DEFAULT_PROMPT_STACKING_SUMMARY_ON_CHUNKS = (
    "Here is a summary of the document.\n" "{summary}\n" "Here is a chunk of the document.\n" "{chunk}\n"
)


def get_formatted_summary_to_add_to_chunks(
    summary: str, chunk: str, chunk_content_template: str = DEFAULT_PROMPT_STACKING_SUMMARY_ON_CHUNKS
):
    return chunk_content_template.format(summary=summary, chunk=chunk)


def add_summary_in_chunks(
    summary: str, chunks: list[FileChunk], chunk_content_template: str = DEFAULT_PROMPT_STACKING_SUMMARY_ON_CHUNKS
):
    for chunk in chunks:
        chunk.content = get_formatted_summary_to_add_to_chunks(
            summary=summary, chunk=chunk.content, chunk_content_template=chunk_content_template
        )
    return chunks


def get_summary_from_document(document, get_file_content_func: Callable, llm_google_service: GoogleLLMService):
    if document.type == FileDocumentType.PDF:
        content = get_file_content_func(document.id)
        return get_summary_from_file(content, llm_google_service, TypeFileToUpload.PDF)
    LOGGER.warning(f"Document type {document.type} not supported for summary extraction." " Returning empty string.")
    return ""


def get_summary_from_file(
    file: str | bytes,
    llm_google_service: GoogleLLMService,
    type_file_to_upload: TypeFileToUpload,
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE_SUMMARY,
) -> str:
    try:
        file_infos = llm_google_service.upload_file(file, type_file_to_upload)
        summary = llm_google_service.complete_with_files(
            messages=[{"role": "user", "content": prompt_template}], files=[file_infos]
        )
        llm_google_service.delete_file(file_infos)
        return summary
    except Exception as e:
        LOGGER.error(f"Error getting summary from document: {e}")
        return None
