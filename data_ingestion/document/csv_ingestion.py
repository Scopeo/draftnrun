from io import StringIO
import pandas as pd
import logging
from typing import Callable, Optional

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument
from data_ingestion.utils import get_chunk_token_count, split_df_by_token_limit

LOGGER = logging.getLogger(__name__)


def ingest_csv_file(
    document: FileDocument,
    get_file_content_func: Callable[[str], bytes | str],
    chunk_size: Optional[int] = 1024,
    **kwargs,
) -> list[FileChunk]:
    result_chunks = []
    content = get_file_content_func(document.id)
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    csv_io = StringIO(content)
    df = pd.read_csv(csv_io)
    df = df.dropna(how="all")
    if df.empty:
        LOGGER.warning(f"File {document.file_name} is empty. Skipping.")
        return []
    if all(isinstance(col, int) for col in df.columns) and list(df.columns) == list(range(len(df.columns))):
        first_row = df.iloc[0]
        if not all(pd.api.types.is_numeric_dtype(type(cell)) for cell in first_row):
            df.columns = first_row
            df = df.iloc[1:]
    total_token_count = get_chunk_token_count(chunk_df=df)
    if total_token_count > chunk_size:
        LOGGER.info(f"Splitting {document.file_name} into chunks")
        df_chunks = split_df_by_token_limit(df=df, max_tokens=chunk_size)
    else:
        LOGGER.info(f"No need to split {document.file_name} into chunks")
        df_chunks = [df]
    for idx, chunk_df in enumerate(df_chunks):
        markdown_content = chunk_df.to_markdown(index=False)
        result_chunks.append(
            FileChunk(
                chunk_id=f"{document.id}_{idx}",
                file_id=document.id,
                content=markdown_content,
                last_edited_ts=document.last_edited_ts,
                document_title=document.file_name,
                bounding_boxes=None,
                url=document.url,
                metadata={**document.metadata},
            )
        )

    return result_chunks
