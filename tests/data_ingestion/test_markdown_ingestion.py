import pytest

from data_ingestion.document.folder_management.folder_management import FileDocumentType, FileDocument
from data_ingestion.document.markdown_ingestion import (
    get_chunks_from_markdown,
)


@pytest.fixture
def mock_file_document():
    file_path = "tests/resources/documents/test_markdown.md"
    return FileDocument(
        id=file_path,
        file_name="test_file",
        type=FileDocumentType.MARKDOWN,
        last_edited_ts="2024-11-26 10:40:40",
        folder_name="/path/to/mock",
    )


def test_get_chunks_from_md(mock_file_document):
    def get_file_content_func(document_id) -> bytes:
        from io import BytesIO
        from pathlib import Path

        return BytesIO(Path(document_id).read_bytes()).getvalue()

    chunks = get_chunks_from_markdown(
        md_doc_to_process=mock_file_document, get_file_content_func=get_file_content_func
    )
    assert len(chunks) == 1
    assert chunks[0].content == "\n# Test\nOk content"
    assert chunks[0].order == 0
    assert chunks[0].file_id == "tests/resources/documents/test_markdown.md"
    assert chunks[0].document_title == "test_file"
    assert chunks[0].last_edited_ts == "2024-11-26 10:40:40"
