import pytest
from engine.agent.types import SourceChunk
from engine.agent.rag.formatter import PAGE_NUMBER_FIELD


# Basic mock with metadata and content
@pytest.fixture
def mock_source_chunk_basic():
    return SourceChunk(
        name="basic",
        document_name="basic",
        url="http://example.com",
        content="Sample content",
        metadata={"author": "Jane Doe", "year": "2021"},
    )


# Mock without metadata
@pytest.fixture
def mock_source_chunk_no_metadata():
    return SourceChunk(
        name="no_metadata",
        document_name="no_metadata",
        url="http://example2.com",
        content="Another sample content",
        metadata={},
    )


# Mock with empty content
@pytest.fixture
def mock_source_chunk_empty_content():
    return SourceChunk(
        name="empty_content",
        document_name="empty_content",
        url="http://example3.com",
        content="",
        metadata={"author": "John Smith"},
    )


# Mock with no URL
@pytest.fixture
def mock_source_chunk_no_url():
    return SourceChunk(
        name="no_url",
        document_name="no_url",
        url="",
        content="Content without URL",
        metadata={"author": "Unknown"},
    )


# Mock with special characters in content and metadata
@pytest.fixture
def mock_source_chunk_special_characters():
    return SourceChunk(
        name="special_characters",
        document_name="special_characters",
        url="http://example4.com",
        content="Content with special characters! @#$%^&*()",
        metadata={"author": "Alice", "description": "Contains !@#$%^&*() symbols"},
    )


# Mock with a large number of metadata fields
@pytest.fixture
def mock_source_chunk_many_metadata():
    return SourceChunk(
        name="many_metadata",
        document_name="many_metadata",
        url="http://example5.com",
        content="Content with a lot of metadata",
        metadata={
            "author": "Jane Doe",
            "year": "2021",
            "publisher": "Tech Press",
            "edition": "Second",
            "ISBN": "123-4567890123",
            "pages": "300",
            "category": "Technology",
            "keywords": "AI, Python, Programming",
        },
    )


@pytest.fixture
def mock_source_chunk_with_page_number():
    return SourceChunk(
        name="with_page_number",
        document_name="with_page_number",
        url="http://example5.com",
        content="Content with a lot of metadata",
        metadata={
            "author": "Jane Doe",
            "year": "2021",
            PAGE_NUMBER_FIELD: "300",
        },
    )
