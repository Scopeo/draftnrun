from unittest import mock

import pytest

from data_ingestion.document.docx_ingestion import (
    _docx_to_md,
    _parse_docx_with_pandoc,
    extract_sections_around_images,
    get_chunks_from_docx,
)
from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType


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
    file_path = "/path/to/file.docx"
    result = _docx_to_md(file_path, extract_image=False)
    assert result == "mock markdown content"
    mock_convert_file.assert_called_once_with(file_path, "md", extra_args=[])


@mock.patch("data_ingestion.document.docx_ingestion.pypandoc.convert_file")
def test_docx_to_md_with_error(mock_convert_file):
    """Test that _docx_to_md returns None on error"""
    mock_convert_file.side_effect = Exception("mock error")
    file_path = "/path/to/file.docx"
    result = _docx_to_md(file_path, extract_image=False)
    assert result is None


@pytest.mark.asyncio
@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
async def test_parse_docx_with_pandoc_no_llm(mock_docx_to_md):
    """Test _parse_docx_with_pandoc without LLM service"""
    mock_docx_to_md.return_value = "mock markdown content"
    file_path = "/path/to/file.docx"

    result = await _parse_docx_with_pandoc(file_path, llm_service_images=None)

    assert result == "mock markdown content"
    mock_docx_to_md.assert_called_once_with(file_path, extract_image=False)


@pytest.mark.asyncio
@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
async def test_parse_docx_with_pandoc_conversion_fails(mock_docx_to_md):
    """Test _parse_docx_with_pandoc returns empty string when conversion fails"""
    mock_docx_to_md.return_value = None
    file_path = "/path/to/file.docx"

    result = await _parse_docx_with_pandoc(file_path, llm_service_images=None)

    assert result == ""


@pytest.mark.asyncio
@mock.patch("data_ingestion.document.docx_ingestion.extract_sections_around_images")
@mock.patch("data_ingestion.document.docx_ingestion.get_image_content_from_path")
@mock.patch("data_ingestion.document.docx_ingestion._docx_to_md")
async def test_parse_docx_with_pandoc_with_llm(mock_docx_to_md, mock_get_image, mock_extract_sections):
    """Test _parse_docx_with_pandoc with LLM service for image descriptions"""
    mock_docx_to_md.return_value = "markdown with ![image](media/image1.png)"
    mock_extract_sections.return_value = {"media/image1.png": {"context": "test context"}}
    mock_get_image.return_value = b"fake image content"

    mock_llm_service = mock.Mock()
    mock_llm_service.get_image_description.return_value = "AI generated description"

    file_path = "/path/to/file.docx"

    with mock.patch("data_ingestion.document.docx_ingestion.Path") as mock_path:
        # Mock the path.rglob to return empty list (no images found on disk)
        mock_path.return_value.parent = mock.MagicMock()
        mock_path.return_value.stem = "file"
        mock_folder = mock.MagicMock()
        mock_folder.rglob.return_value = []
        mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value = mock_folder

        result = await _parse_docx_with_pandoc(file_path, llm_service_images=mock_llm_service)

        # Since no images are found on disk, result should be the original markdown
        assert result == "markdown with ![image](media/image1.png)"
        mock_docx_to_md.assert_called_once_with(file_path, extract_image=True)


@pytest.mark.asyncio
async def test_get_chunks_from_docx(mock_file_document):
    """Test get_chunks_from_docx with successful parsing"""
    mock_parser = mock.AsyncMock(return_value="mock markdown content")
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")

    chunks = await get_chunks_from_docx(
        mock_file_document,
        mock_get_file_content,
        docx_parser=mock_parser,
        chunk_size=1024,
        chunk_overlap=0,
    )

    assert len(chunks) == 1
    assert chunks[0].content == "\nmock markdown content"
    assert chunks[0].order == 0
    assert chunks[0].file_id == "/path/to/mock/file.docx"
    assert chunks[0].document_title == "file.docx"
    assert chunks[0].last_edited_ts == "2024-11-26 10:40:40"


@pytest.mark.asyncio
async def test_get_chunks_from_docx_with_error(mock_file_document):
    """Test get_chunks_from_docx raises exception on error"""
    mock_parser = mock.AsyncMock(side_effect=Exception("mock error"))
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")

    with pytest.raises(Exception, match="Error processing DOCX file.docx"):
        await get_chunks_from_docx(
            mock_file_document,
            mock_get_file_content,
            docx_parser=mock_parser,
            chunk_size=1024,
            chunk_overlap=0,
        )


@pytest.mark.asyncio
async def test_get_chunks_from_docx_multiple_chunks(mock_file_document):
    """Test get_chunks_from_docx with content that creates multiple chunks"""
    mock_parser = mock.AsyncMock(return_value="# mock markdown content " * 1000)
    mock_get_file_content = mock.Mock(return_value=b"fake docx content")

    chunks = await get_chunks_from_docx(
        mock_file_document,
        mock_get_file_content,
        docx_parser=mock_parser,
        chunk_size=1024,
        chunk_overlap=0,
    )

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.order == i
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
