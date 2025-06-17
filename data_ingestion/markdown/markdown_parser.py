from enum import Enum
from typing import Optional

from anytree import AnyNode


class MarkdownLevel(Enum):
    ROOT = 0
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4
    H5 = 5
    H6 = 6
    TEXT = 7


class MarkdownNode(AnyNode):
    def __init__(
        self,
        content: str,
        level: MarkdownLevel,
        parent: Optional["MarkdownNode"] = None,
        children: Optional[list["MarkdownNode"]] = None,
    ):
        super().__init__(parent=parent, children=children)
        self.level = level
        self.content = content

    @property
    def formatted_path(self):
        """Formats the path to this node as a list of titles."""
        if len(self.path) == 1:
            return ""

        formatted_path = " > ".join([node.content.strip() for node in self.path[:-1]])
        return formatted_path

    @property
    def formatted_content(self):
        if self.level == MarkdownLevel.TEXT:
            return self.content
        else:
            return f"{'#' * self.level.value} {self.content}"


def _get_header_level(line: str) -> MarkdownLevel:
    """
    Get the header level of a markdown line. E.g.:
    - "# A Title" -> MarkdownLevel.H1
    - "##Another title" -> MarkdownLevel.H2
    - "some text ###" -> MarkdownLevel.TEXT
    Args:
        line (str): A line of markdown text
    Returns:
        MarkdownLevel: The header level of the line
    """
    header_level = 0
    for char in line:
        if char == "#":
            header_level += 1
        else:
            break
    if header_level == 0 or header_level > 6:
        return MarkdownLevel.TEXT
    return MarkdownLevel(header_level)


def _get_header_text(line: str) -> str:
    """
    Get the text of a markdown header line. E.g.:
    - "# A Title" -> "A Title"
    - "##Another title" -> "Another title"
    - "some text ###" -> ValueError
    Args:
        line (str): A line of markdown text
    Returns:
        str: The text of the header line
    """
    if not line.startswith("#"):
        raise ValueError("Line is not a header")
    return line.strip("#").strip()


def parse_markdown_to_tree(file_content: str, file_name: str) -> MarkdownNode:
    root = MarkdownNode(file_name, level=MarkdownLevel.ROOT)
    current_node = root

    for line in file_content.splitlines():
        header_level = _get_header_level(line)
        if header_level == MarkdownLevel.TEXT and current_node.level == MarkdownLevel.TEXT:
            current_node.content += line + "\n"
        elif header_level == MarkdownLevel.TEXT:
            new_node = MarkdownNode(content=line, level=header_level, parent=current_node)
            current_node = new_node
        else:
            header = _get_header_text(line)
            while current_node.level.value >= header_level.value:
                current_node = current_node.parent
            new_node = MarkdownNode(content=header, level=header_level, parent=current_node)
            current_node = new_node
    return root
