from io import BytesIO
import pandas as pd
import logging
from typing import Callable, Optional


from data_ingestion.document.folder_management.folder_management import FileDocument, FileChunk
from data_ingestion.utils import get_chunk_token_count, split_df_by_token_limit

LOGGER = logging.getLogger(__name__)


def ingest_excel_file(
    document: FileDocument,
    get_file_content_func: Callable[[FileDocument], str],
    chunk_size: Optional[int] = 512,
    **kwargs,
) -> list[FileChunk]:
    result_chunks = []
    content_to_process = BytesIO(get_file_content_func(document.id))
    xls = pd.ExcelFile(content_to_process)
    LOGGER.info(f"File {document.file_name} loaded.")
    sheet_names = xls.sheet_names
    for sheet_name in sheet_names:
        df = pd.read_excel(content_to_process, sheet_name=sheet_name, header=None)
        total_token_count = get_chunk_token_count(chunk_df=df)
        if total_token_count > chunk_size:
            LOGGER.info(f"Splitting {sheet_name} into chunks")
            df_chunks = split_df_by_token_limit(df=df, max_tokens=chunk_size)
        else:
            LOGGER.info(f"No need to split {sheet_name} into chunks")
            df_chunks = [df]

        for idx, chunk_df in enumerate(df_chunks):
            markdown_content = chunk_df.to_markdown(index=False)
            result_chunks.append(
                FileChunk(
                    chunk_id=f"{document.id}_{sheet_name}_{idx}",
                    file_id=document.id,
                    content=markdown_content,
                    last_edited_ts=document.last_edited_ts,
                    document_title=document.file_name,
                    bounding_boxes=None,
                    url=document.url,
                    metadata={**document.metadata, "sheet": sheet_name, "chunk_index": idx + 1},
                )
            )

    return result_chunks
