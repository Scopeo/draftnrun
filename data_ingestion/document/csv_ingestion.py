from io import StringIO
import pandas as pd
from typing import Callable

from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument


def ingest_csv_file(
    document: FileDocument,
    get_file_content_func: Callable[[FileDocument], str],
    **kwargs,
) -> list[FileChunk]:
    result_chunks = []
    content = get_file_content_func(document.id)
    # If content is bytes, decode to string
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    csv_io = StringIO(content)
    df = pd.read_csv(csv_io)
    markdown_content = df.to_markdown(index=False)
    result_chunks.append(
        FileChunk(
            chunk_id=f"{document.file_name}",
            file_id=document.file_name,
            content=markdown_content,
            last_edited_ts=document.last_edited_ts,
            document_title=document.file_name,
            bounding_boxes=[],
            url=document.url,
            metadata=document.metadata,
        )
    )
    return result_chunks
