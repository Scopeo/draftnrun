import asyncio
import uuid
from unittest.mock import Mock, patch

import pytest

from data_ingestion.document.document_chunking import get_chunks_dataframe_from_doc
from data_ingestion.document.folder_management.folder_management import FileChunk, FileDocument, FileDocumentType


@pytest.fixture
def mock_file_document():
    return FileDocument(
        id="dummy_id",
        last_edited_ts="2023-01-01T00:00:00Z",
        type=FileDocumentType.PDF,
        file_name="dummy_file",
        folder_name="dummy_folder_ids",
    )


@pytest.fixture
def mock_file_chunk():
    return FileChunk(
        chunk_id=str(uuid.uuid4()),
        file_id="dummy_id",
        order=0,
        content="dummy content",
        bounding_boxes=[{"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4, "page": 1}],
        last_edited_ts="2023-01-01T00:00:00Z",
        document_title="dummy_title",
    )


def test_get_chunks_dataframe_from_docs(mock_file_document, mock_file_chunk):
    mock_processor = Mock(return_value=[mock_file_chunk])
    llm_mock = Mock()
    document_chunk_mapping = {
        FileDocumentType.PDF.value: mock_processor,
    }
    docs_to_process = mock_file_document

    with patch("data_ingestion.document.document_chunking.LOGGER") as mock_logger:
        result_df = asyncio.run(
            get_chunks_dataframe_from_doc(
                document=docs_to_process,
                document_chunk_mapping=document_chunk_mapping,
                llm_service=llm_mock,
            )
        )

    mock_processor.assert_called_once_with(mock_file_document, chunk_size=1024)
    # Verify that logging occurred with the document processing start message
    assert mock_logger.info.called
    assert any(
        "[DOCUMENT_PROCESSING] Starting processing for document 'dummy_file'" in str(call)
        for call in mock_logger.info.call_args_list
    )

    # Verify the dataframe has the expected structure
    assert len(result_df) == 1
    assert "chunk_id" in result_df.columns
    assert "file_id" in result_df.columns
    assert "content" in result_df.columns
    assert "last_edited_ts" in result_df.columns
    assert "metadata" in result_df.columns
    assert "document_title" in result_df.columns
    assert "bounding_boxes" in result_df.columns
    assert "url" in result_df.columns
    assert "order" in result_df.columns

    # Verify chunk_id is a valid UUID format and matches the fixture
    chunk_id_value = result_df["chunk_id"].iloc[0]
    uuid.UUID(chunk_id_value)  # Will raise ValueError if not a valid UUID
    assert chunk_id_value == mock_file_chunk.chunk_id

    # Verify other fields match expected values
    assert result_df["file_id"].iloc[0] == "dummy_id"
    assert result_df["content"].iloc[0] == "dummy content"
    assert result_df["last_edited_ts"].iloc[0] == "2023-01-01T00:00:00Z"
    assert result_df["metadata"].iloc[0] == "{}"
    assert result_df["document_title"].iloc[0] == "dummy_title"
    assert result_df["bounding_boxes"].iloc[0] == '[{"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4, "page": 1}]'
    assert result_df["url"].iloc[0] == "None"
    assert result_df["order"].iloc[0] == 0
