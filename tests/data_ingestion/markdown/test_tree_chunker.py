from unittest.mock import MagicMock

import pytest

from data_ingestion.markdown.markdown_parser import MarkdownLevel, MarkdownNode
from data_ingestion.markdown.tree_chunker import TreeChunker


@pytest.fixture
def mock_encoding():
    mock_encoding = MagicMock()
    mock_encoding.encode.side_effect = lambda text: list(text.encode("utf-8"))
    return mock_encoding


@pytest.fixture
def chunker(mock_encoding):
    chunker = TreeChunker(model_name="gpt-4o-mini", chunk_size=80)
    chunker._encoding = mock_encoding
    return chunker


def test_count_tokens(chunker):
    text = "Hello, world!"
    expected_token_count = len(text.encode("utf-8"))
    assert chunker._count_tokens(text) == expected_token_count


def test_chunk_tree(chunker):
    root = MarkdownNode("root", level=MarkdownLevel.ROOT)
    child1 = MarkdownNode(level=MarkdownLevel.H1, content="child1", parent=root)
    child2 = MarkdownNode(level=MarkdownLevel.TEXT, content="content1", parent=child1)
    child2 = MarkdownNode(level=MarkdownLevel.H2, content="child2", parent=child1)
    child3 = MarkdownNode(level=MarkdownLevel.H3, content="child3", parent=child2)  # noqa : F841

    chunks = chunker.chunk_tree(root)

    assert len(chunks) == 1
    assert chunks[0].formatted_path == " root\n# child1"
    assert chunks[0].content == "content1\n\n## child2\n\n### child3"
