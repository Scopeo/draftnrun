from typing import Callable, Optional
from functools import partial
import logging
import json

import pandas as pd

from data_ingestion.document.docx_ingestion import get_chunks_from_docx
from data_ingestion.document.markdown_ingestion import get_chunks_from_markdown
from data_ingestion.document.summary_from_document import get_formatted_summary_to_add_to_chunks
from data_ingestion.document.pdf_vision_ingestion import create_chunks_from_document
from data_ingestion.document.folder_management.folder_management import (
    FileChunk,
    FileDocument,
    FileDocumentType,
)
from engine.llm_services.llm_service import LLMService

LOGGER = logging.getLogger(__name__)
FileProcessor = Callable[[FileDocument], list[FileChunk]]


def document_chunking_mapping(
    vision_ingestion_service: Optional[LLMService] = None,
    llm_service: Optional[LLMService] = None,
    get_file_content_func: Optional[Callable[[FileDocument], str]] = None,
    docx_overlapping_size: int = 50,
) -> dict[FileDocumentType, FileProcessor]:

    document_chunking_mapping = {
        FileDocumentType.PDF.value: partial(
            create_chunks_from_document,
            google_llm_service=vision_ingestion_service,
            openai_llm_service=llm_service,
            get_file_content=get_file_content_func,
        ),
        FileDocumentType.DOCX.value: partial(
            get_chunks_from_docx,
            get_file_content_func=get_file_content_func,
            chunk_overlap=docx_overlapping_size,
        ),
        FileDocumentType.MARKDOWN.value: partial(
            get_chunks_from_markdown,
            get_file_content_func=get_file_content_func,
            chunk_overlap=docx_overlapping_size,
        ),
    }
    return document_chunking_mapping


def get_chunks_dataframe_from_doc(
    document: FileDocument,
    document_chunk_mapping: dict[FileDocumentType, FileProcessor],
    llm_service: LLMService,
    json_type_fields: list[str] = ["bounding_boxes", "metadata"],
    add_doc_description_to_chunks: bool = False,
    documents_summary_func: Optional[Callable] = None,
    add_summary_in_chunks_func: Optional[Callable] = None,
    default_chunk_size: int = 1024,
) -> pd.DataFrame:
    all_chunks = []
    LOGGER.info(f"Processing document {document.file_name} of type {document.type}")
    description_doc = None
    if add_doc_description_to_chunks:
        if documents_summary_func is None or add_summary_in_chunks_func is None:
            raise ValueError("No summary function / put summary function provided for documents")
        description_doc = documents_summary_func(document)

    chunk_size_doc = default_chunk_size
    if description_doc is not None:
        summary_token_size = llm_service.get_token_size(
            get_formatted_summary_to_add_to_chunks(summary=description_doc, chunk="")
        )
        chunk_size_doc -= summary_token_size
    if chunk_size_doc <= 0:
        LOGGER.warning(f"Summary token size is too big for document {document.id}")
        description_doc = ""
        chunk_size_doc = default_chunk_size
    chunks = document_chunk_mapping[document.type.value](document, chunk_size=chunk_size_doc)
    if description_doc is not None:
        chunks = add_summary_in_chunks_func(
            summary=description_doc,
            chunks=chunks,
        )
    all_chunks.extend(chunks)
    chunks_df = pd.DataFrame([chunk.model_dump() for chunk in all_chunks])
    chunks_df.columns = [col.lower() for col in chunks_df.columns]
    for field in json_type_fields:
        lower_field = field.lower()
        if lower_field in chunks_df.columns:
            chunks_df[lower_field] = chunks_df[lower_field].apply(json.dumps)
    chunks_df = chunks_df.astype(str)
    return chunks_df
