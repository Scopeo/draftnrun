from io import BytesIO
import pandas as pd
import logging
from typing import Callable


from data_ingestion.document.folder_management.folder_management import FileDocument, FileChunk

LOGGER = logging.getLogger(__name__)


def ingest_excel_file(
    document: FileDocument,
    get_file_content_func: Callable[[FileDocument], str],
    **kwargs,
) -> list[FileChunk]:
    result_chunks = []
    content_to_process = BytesIO(get_file_content_func(document.id))
    xls = pd.ExcelFile(content_to_process)
    LOGGER.info(f"File {document.file_name} loaded.")
    sheet_names = xls.sheet_names
    for sheet_name in sheet_names:
        df = pd.read_excel(content_to_process, sheet_name=sheet_name, header=None)
        markdown_content = df.to_markdown(index=False)
        result_chunks.append(
            FileChunk(
                chunk_id=f"{document.file_name}_{sheet_name}",
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
