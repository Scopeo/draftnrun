import base64
import json
import logging
import mimetypes
from typing import Callable, Optional

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.document.markdown_ingestion import chunk_markdown
from engine.llm_services.llm_service import OCRService
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


async def get_chunks_from_document_with_mistral_ocr(
    document: FileDocument,
    get_file_content: Callable[[str], bytes | str],
    mistral_ocr_api_key: str,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
    get_presigned_url: Optional[Callable[[str], str | None]] = None,
    **kwargs,
) -> list[FileChunk]:
    if not mistral_ocr_api_key:
        raise ValueError("mistral_ocr_api_key is required for MISTRAL_OCR mode")

    if get_presigned_url:
        file_data_url = get_presigned_url(document.id)
    else:
        content_bytes = get_file_content(document.id)
        if isinstance(content_bytes, str):
            content_bytes = content_bytes.encode("utf-8")
        mime_type = mimetypes.guess_type(document.file_name)[0] or "application/pdf"
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        file_data_url = f"data:{mime_type};base64,{b64}"

    ocr = OCRService(
        trace_manager=TraceManager(project_name="ingestion"),
        provider="mistral",
        model_name="mistral-ocr-latest",
        api_key=mistral_ocr_api_key,
    )
    messages = [
        {
            "role": "user",
            "content": [{"file": {"file_data": file_data_url}}],
        }
    ]
    ocr_result_json = await ocr.get_ocr_text_async(messages)
    ocr_result = json.loads(ocr_result_json)
    pages = ocr_result.get("pages", [])
    markdown_text = "\n\n".join(page.get("markdown", "") for page in pages if page.get("markdown"))

    if not markdown_text:
        LOGGER.warning(f"Mistral OCR returned empty markdown for {document.file_name}")
        return []

    return chunk_markdown(
        document_to_process=document,
        content=markdown_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
