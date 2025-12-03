import pytest
from unittest import mock
from data_ingestion.document.folder_management.folder_management import FileDocumentType, FileDocument

from data_ingestion.document.docx_ingestion import (
    _docx_to_md,
    _docx_to_md_safe_mode,
    extract_sections_around_images,
    get_chunks_from_docx,
)


@pytest.fixture
def mock_file_document():
    file_path = "/path/to/mock/file.docx"
    return FileDocument(
        id=file_path,
        file_name="file.docx",
        type=FileDocumentType.DOCX,
        last_edited_ts="2024-11-26 10:40:40",
        folder_name="/path/to/mock",
    )


@mock.patch("data_ingestion.document.docx_ingestion.pypandoc.convert_file")
def test_docx_to_md(mock_convert_file):
    mock_convert_file.return_value = "mock markdown content"
    fake_docx_content = b"PK\x03\x04 fake docx content"
    result = _docx_to_md(fake_docx_content)
    assert result == "mock markdown content"
    mock_convert_file.assert_called_once()

    called_args, called_kwargs = mock_convert_file.call_args
    assert called_args[0].endswith(".docx")
    assert called_args[1] == "md"
    assert called_kwargs["extra_args"] == []


@mock.patch("data_ingestion.document.docx_ingestion.pypandoc.convert_file")
@mock.patch("data_ingestion.document.docx_ingestion.tempfile.NamedTemporaryFile")
def test_docx_to_md_safe_mode(mock_tempfile, mock_convert_file):
    mock_tempfile.return_value.__enter__.return_value.name = "/path/to/temp/file.docx"
    mock_convert_file.return_value = "mock markdown content"

    fake_docx_content = b"mock docx content"

    result = _docx_to_md_safe_mode(fake_docx_content)
    assert result == "mock markdown content"

    mock_convert_file.assert_called_once_with("/path/to/temp/file.docx", "md", extra_args=[])


@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
def test_get_chunks_from_docx(mock_docx_to_md, mock_file_document):
    mock_docx_to_md.return_value = "mock markdown content"
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")
    chunks = get_chunks_from_docx(mock_file_document, mock_get_file_content)
    assert len(chunks) == 1
    assert chunks[0].content == "\nmock markdown content"
    assert chunks[0].chunk_id == "/path/to/mock/file.docx_0"
    assert chunks[0].file_id == "/path/to/mock/file.docx"
    assert chunks[0].document_title == "file.docx"
    assert chunks[0].last_edited_ts == "2024-11-26 10:40:40"


@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
def test_get_chunks_from_docx_with_error(mock_docx_to_md, mock_file_document):
    mock_docx_to_md.side_effect = [Exception("mock error"), "mock markdown content"]
    mock_docx_to_md.return_value = "mock markdown content"
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")
    chunks = get_chunks_from_docx(mock_file_document, mock_get_file_content)
    assert len(chunks) == 1
    assert chunks[0].content == "\nmock markdown content"
    assert chunks[0].chunk_id == "/path/to/mock/file.docx_0"
    assert chunks[0].file_id == "/path/to/mock/file.docx"
    assert chunks[0].document_title == "file.docx"
    assert chunks[0].last_edited_ts == "2024-11-26 10:40:40"


@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
def test_get_chunks_from_docx_multiple_chunks(mock_docx_to_md, mock_file_document):
    mock_docx_to_md.return_value = "# mock markdown content " * 1000
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")
    chunks = get_chunks_from_docx(mock_file_document, mock_get_file_content)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == f"/path/to/mock/file.docx_{i}"
        assert chunk.file_id == "/path/to/mock/file.docx"
        assert chunk.document_title == "file.docx"
        assert chunk.last_edited_ts == "2024-11-26 10:40:40"


def test_extract_sections_around_images_no_images():
    markdown_text = "This is a test document. It has no images."
    result = extract_sections_around_images(markdown_text)
    assert result == {}


def test_extract_sections_around_images_single_image():
    markdown_text = (
        "This is a test document. It has an image ![alt text](image1.png) in the middle. Here is some more text."
    )
    result = extract_sections_around_images(markdown_text)
    assert len(result.keys()) == 1
    assert "image1.png" in result.keys()
    assert (
        result["image1.png"]["context"]
        == "This is a test document. It has an image ![alt text](image1.png) in the middle. Here is some more text."
    )


def test_extract_sections_around_images_multiple_images():
    markdown_text = (
        "This is a test document. It has an image ![alt text](image1.png) in the middle. "
        "Here is some more text. Another image ![alt text](image2.png) is here. "
        "Finally, some concluding text."
    )
    result = extract_sections_around_images(markdown_text)
    assert len(result.keys()) == 2
    assert "image1.png" in result.keys()
    assert (
        result["image1.png"]["context"]
        == "This is a test document. It has an image ![alt text](image1.png) in the middle. "
        "Here is some more text. Another image ![alt text](image2.png) is here. "
        "Finally, some"
    )
    assert "image2.png" in result.keys()
    assert (
        result["image2.png"]["context"] == "ument. It has an image ![alt text](image1.png) in the middle. "
        "Here is some more text. Another image ![alt text](image2.png) is here. "
        "Finally, some concluding text."
    )


def test_extract_sections_around_images_at_edges():
    markdown_text = (
        "![alt text](image1.png) This is a test document. It has an image at the start. "
        "Here is some more text. Another image is at the end ![alt text](image2.png)."
    )
    result = extract_sections_around_images(markdown_text)
    assert len(result.keys()) == 2
    assert "image1.png" in result.keys()
    assert (
        result["image1.png"]["context"]
        == "![alt text](image1.png) This is a test document. It has an image at the start. "
        "Here is some more text. Another image is at "
    )
    assert "image2.png" in result.keys()
    assert (
        result["image2.png"]["context"] == " a test document. It has an image at the start. "
        "Here is some more text. Another image is at the end ![alt text](image2.png)."
    )
