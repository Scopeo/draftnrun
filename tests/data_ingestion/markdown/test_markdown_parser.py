import pytest

from data_ingestion.markdown.markdown_parser import (
    MarkdownLevel,
    MarkdownNode,
    _get_header_level,
    _get_header_text,
    parse_markdown_to_tree,
)
from data_ingestion.markdown.tree_utils import are_trees_equal


def test_get_header_level():
    assert _get_header_level("# A Title") == MarkdownLevel.H1
    assert _get_header_level("## Another title") == MarkdownLevel.H2
    assert _get_header_level("some text ###") == MarkdownLevel.TEXT
    assert _get_header_level("###### A Level 6 Header") == MarkdownLevel.H6
    assert _get_header_level("####### Invalid Header") == MarkdownLevel.TEXT


def test_get_header_text():
    assert _get_header_text("# A Title") == "A Title"
    assert _get_header_text("## Another title") == "Another title"
    with pytest.raises(ValueError):
        _get_header_text("some text ###")


def test_markdown_node():
    root = MarkdownNode("root", MarkdownLevel.ROOT)
    child1 = MarkdownNode("child1", MarkdownLevel.H1, parent=root)
    assert child1.parent == root
    assert child1.level == MarkdownLevel.H1
    assert child1.content == "child1"
    assert child1.formatted_content == "# child1"


def test_parse_markdown_to_tree():
    file_content = (
        "text hanging from the root\n## Hello, how are you\nThis is a test paragraph.\n"
        "### Subtitle 1\nThis is another test paragraph.\n## Fine, thank you"
    )
    file_name = "test_file.md"
    actual_tree = parse_markdown_to_tree(file_content, file_name)

    expected_tree = MarkdownNode(
        file_name,
        MarkdownLevel.ROOT,
        children=[
            MarkdownNode("text hanging from the root", MarkdownLevel.TEXT),
            MarkdownNode(
                "Hello, how are you",
                MarkdownLevel.H2,
                children=[
                    MarkdownNode("This is a test paragraph.", MarkdownLevel.TEXT),
                    MarkdownNode(
                        "Subtitle 1",
                        MarkdownLevel.H3,
                        children=[
                            MarkdownNode(
                                "This is another test paragraph.",
                                MarkdownLevel.TEXT,
                            ),
                        ],
                    ),
                ],
            ),
            MarkdownNode("Fine, thank you", MarkdownLevel.H2),
        ],
    )

    assert are_trees_equal(expected_tree, actual_tree, lambda node: node.content)
