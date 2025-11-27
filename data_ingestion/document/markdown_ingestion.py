from typing import Callable

from data_ingestion.document.folder_management.folder_management import BaseDocument, FileChunk
from data_ingestion.markdown.tree_chunker import parse_markdown_to_chunks

CHUNK_SIZE = 750
CHUNK_OVERLAP = 30


def get_md_from_bytes(file_content: bytes) -> str:
    """ """
    return file_content.decode("utf-8")


def get_chunks_from_markdown(
    md_doc_to_process: BaseDocument,
    get_file_content_func: Callable[[str], bytes | str],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
):
    md_content = get_md_from_bytes(get_file_content_func(md_doc_to_process.id))
    return chunk_markdown(
        document_to_process=md_doc_to_process,
        content=md_content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def build_chunk(document: BaseDocument, content: str, chunk_id: str) -> FileChunk:
    return FileChunk(
        chunk_id=chunk_id,
        file_id=str(document.id),
        content=content,
        url=document.url,
        last_edited_ts=document.last_edited_ts if document.last_edited_ts else None,
        document_title=document.file_name if document.file_name else None,
        bounding_boxes=[],
        metadata=document.metadata if document.metadata else {},
    )


def chunk_markdown(
    document_to_process: BaseDocument,
    content: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[FileChunk]:
    tree_chunks = parse_markdown_to_chunks(
        file_content=content,
        file_name=document_to_process.file_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return [
        build_chunk(
            document=document_to_process,
            content=tree_chunk.content,
            chunk_id=f"{str(document_to_process.id)}_{i}",
        )
        for i, tree_chunk in enumerate(tree_chunks)
    ]
