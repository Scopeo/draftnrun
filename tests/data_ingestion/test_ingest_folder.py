import asyncio
import pytest
import pandas as pd
from unittest.mock import Mock, patch
from data_ingestion.document.document_chunking import get_chunks_dataframe_from_doc
from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FileChunk


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
        chunk_id="chunk_1",
        document_id="dummy_id",
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

    expected_data = {
        "chunk_id": ["chunk_1"],
        "file_id": ["dummy_id"],
        "content": ["dummy content"],
        "last_edited_ts": ["2023-01-01T00:00:00Z"],
        "metadata": ["{}"],
        "document_title": ["dummy_title"],
        "bounding_boxes": ['[{"xmin": 1, "ymin": 2, "xmax": 3, "ymax": 4, "page": 1}]'],
        "url": ["None"],
    }
    expected_df = pd.DataFrame(expected_data)
    pd.testing.assert_frame_equal(result_df, expected_df)
