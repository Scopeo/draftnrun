import inspect
from typing import Callable, Optional
from functools import partial
import logging
import json

import pandas as pd

from data_ingestion.document.docx_ingestion import get_chunks_from_docx
from data_ingestion.document.markdown_ingestion import get_chunks_from_markdown
from data_ingestion.document.pdf_vision_ingestion import create_chunks_from_document
from data_ingestion.document.parsing_pdf_ingestion import create_chunks_from_document_without_llm
from data_ingestion.document.excel_ingestion import ingest_excel_file
from data_ingestion.document.csv_ingestion import ingest_csv_file
from data_ingestion.document.folder_management.folder_management import (
    BaseDocument,
    FileChunk,
    FileDocument,
    FileDocumentType,
)
from ingestion_script.utils import ORDER_COLUMN_NAME
from engine.llm_services.llm_service import CompletionService, VisionService

LOGGER = logging.getLogger(__name__)
FileProcessor = Callable[[FileDocument], list[FileChunk]]


def document_chunking_mapping(
    vision_ingestion_service: Optional[VisionService] = None,
    llm_service: Optional[CompletionService] = None,
    get_file_content_func: Optional[Callable[[FileDocument], str]] = None,
    overlapping_size: int = 50,
    chunk_size: Optional[int] = 1024,
    use_llm_for_pdf: bool = True,
) -> dict[FileDocumentType, FileProcessor]:

    if use_llm_for_pdf:
        pdf_processor = partial(
            create_chunks_from_document,
            google_llm_service=vision_ingestion_service,
            openai_llm_service=llm_service,
            get_file_content=get_file_content_func,
        )
        LOGGER.info("Using LLM-based PDF processing")
    else:
        pdf_processor = partial(
            create_chunks_from_document_without_llm,
            get_file_content=get_file_content_func,
            chunk_size=chunk_size,
            chunk_overlap=overlapping_size,
        )
        LOGGER.info("Using non-LLM PDF processing with pymupdf4llm")

    document_chunking_mapping = {
        FileDocumentType.PDF.value: pdf_processor,
        FileDocumentType.DOCX.value: partial(
            get_chunks_from_docx,
            get_file_content_func=get_file_content_func,
            chunk_overlap=overlapping_size,
        ),
        FileDocumentType.MARKDOWN.value: partial(
            get_chunks_from_markdown,
            get_file_content_func=get_file_content_func,
            chunk_overlap=overlapping_size,
        ),
        FileDocumentType.EXCEL.value: partial(
            ingest_excel_file,
            get_file_content_func=get_file_content_func,
            chunk_size=chunk_size,
        ),
        FileDocumentType.GOOGLE_SHEET.value: partial(
            ingest_excel_file,
            get_file_content_func=get_file_content_func,
            chunk_size=chunk_size,
        ),
        FileDocumentType.CSV.value: partial(
            ingest_csv_file,
            get_file_content_func=get_file_content_func,
            chunk_size=chunk_size,
        ),
    }
    return document_chunking_mapping


async def get_chunks_dataframe_from_doc(
    document: BaseDocument,
    document_chunk_mapping: dict[FileDocumentType, FileProcessor],
    llm_service: Optional[CompletionService] = None,
    json_type_fields: list[str] = ["bounding_boxes", "metadata"],
    add_doc_description_to_chunks: bool = False,
    documents_summary_func: Optional[Callable] = None,
    add_summary_in_chunks_func: Optional[Callable] = None,
    default_chunk_size: Optional[int] = 1024,
) -> pd.DataFrame:
    all_chunks = []

    # Comprehensive logging for document processing
    LOGGER.info(f"[DOCUMENT_PROCESSING] Starting processing for document '{document.file_name}'")
    LOGGER.info(
        f"[DOCUMENT_PROCESSING] Document details - ID: '{document.id}', "
        f"Type: '{document.type.value}', Folder: '{document.folder_name}'"
    )

    # Log which processor will be used
    processor_func = document_chunk_mapping.get(document.type.value)
    if processor_func:
        try:
            processor_name = processor_func.func.__name__
        except (AttributeError, TypeError):
            processor_name = str(processor_func)
        LOGGER.info(
            f"[PROCESSOR_ROUTING] Using processor '{processor_name}' for file type "
            f"'{document.type.value}' on file '{document.file_name}'"
        )
    else:
        LOGGER.error(
            f"[PROCESSOR_ROUTING] FAILED - No processor found for file type "
            f"'{document.type.value}' on file '{document.file_name}'"
        )
        available_types = list(document_chunk_mapping.keys())
        raise ValueError(
            f"No processor available for file type '{document.type.value}'. Available types: {available_types}"
        )

    # TODO: add summary to chunks when we will have a gemini functional service
    # description_doc = None
    # if add_doc_description_to_chunks:
    #     if documents_summary_func is None or add_summary_in_chunks_func is None:
    #         raise ValueError("No summary function / put summary function provided for documents")
    #     description_doc = documents_summary_func(document)

    chunk_size_doc = default_chunk_size
    LOGGER.info(f"[DOCUMENT_PROCESSING] Using chunk size: {chunk_size_doc} for '{document.file_name}'")

    # if description_doc is not None:
    #     summary_token_size = llm_service.get_token_size(
    #         get_formatted_summary_to_add_to_chunks(summary=description_doc, chunk="")
    #     )
    #     chunk_size_doc -= summary_token_size
    # if chunk_size_doc <= 0:
    #     LOGGER.warning(f"Summary token size is too big for document {document.id}")
    #     description_doc = ""
    #     chunk_size_doc = default_chunk_size

    try:
        LOGGER.info(f"[PROCESSOR_EXECUTION] Starting '{processor_name}' processing for '{document.file_name}'")
        chunks = document_chunk_mapping[document.type.value](document, chunk_size=chunk_size_doc)
        if inspect.isawaitable(chunks):  # await if necessary
            chunks = await chunks
        LOGGER.info(
            f"[PROCESSOR_EXECUTION] Successfully processed '{document.file_name}' - Generated {len(chunks)} chunks"
        )
    except Exception as e:
        LOGGER.error(
            f"[PROCESSOR_EXECUTION] FAILED - Error processing '{document.file_name}' with '{processor_name}': {str(e)}"
        )
        raise
    # if description_doc is not None:
    #     chunks = add_summary_in_chunks_func(
    #         summary=description_doc,
    #         chunks=chunks,
    #     )
    all_chunks.extend(chunks)
    chunks_df = pd.DataFrame([chunk.model_dump() for chunk in all_chunks])
    chunks_df.columns = [col.lower() for col in chunks_df.columns]
    if ORDER_COLUMN_NAME not in chunks_df.columns or chunks_df[ORDER_COLUMN_NAME].isna().all():
        chunks_df[ORDER_COLUMN_NAME] = range(len(chunks_df))
    for field in json_type_fields:
        lower_field = field.lower()
        if lower_field in chunks_df.columns:
            chunks_df[lower_field] = chunks_df[lower_field].apply(json.dumps)
    for col in chunks_df.columns:
        if col != ORDER_COLUMN_NAME:
            chunks_df[col] = chunks_df[col].astype(str)
    return chunks_df
