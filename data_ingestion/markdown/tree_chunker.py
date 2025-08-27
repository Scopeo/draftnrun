import logging
from functools import partial
from typing import Optional

import tiktoken
from llama_index.core.node_parser import SentenceSplitter

from data_ingestion.markdown.markdown_parser import (
    MarkdownLevel,
    MarkdownNode,
    parse_markdown_to_tree,
)

LOGGER = logging.getLogger(__name__)


class TreeChunk:
    def __init__(self, content: str, level: MarkdownLevel, ancestors: list["TreeChunk"] = None):
        self.content = content
        self.level = level
        self.ancestors = ancestors if ancestors else []

    @property
    def formatted_path(self) -> str:
        path = [ancestor.content for ancestor in self.ancestors]
        return "\n".join(path)

    def copy(self):
        return TreeChunk(content=self.content, level=self.level, ancestors=self.ancestors)

    def __str__(self):
        return self.content

    def __add__(self, other: "TreeChunk") -> "TreeChunk":
        if not isinstance(other, TreeChunk):
            return NotImplemented
        if len(self.ancestors) > 0 and len(other.ancestors) > 0 and self.ancestors[0] == other.ancestors[0]:
            new_self = self.copy()
            new_self.ancestors = self.ancestors[1:]
            new_other = other.copy()
            new_other.ancestors = other.ancestors[1:]
            added_chunk = new_self + new_other
            added_chunk.ancestors = [self.ancestors[0]] + added_chunk.ancestors
            return added_chunk

        else:
            new_content = "\n\n".join(
                filter(
                    None,
                    [
                        self.formatted_path.strip(),
                        self.content.strip(),
                        other.formatted_path.strip(),
                        other.content.strip(),
                    ],
                )
            )

            return TreeChunk(
                content=new_content,
                level=min(self.level, other.level, key=lambda x: x.value),
                ancestors=[],
            )


class TreeChunker:
    """Class to generate chunks of markdown content.
    Markdown node are combined into chunks of a maximum token size."""

    def __init__(self, model_name: str = "gpt-4o-mini", chunk_size: int = 2048, chunk_overlap: int = 0):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._encoding = tiktoken.encoding_for_model(model_name)

    def _count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def _split_text(self, chunk: TreeChunk) -> list[TreeChunk]:
        splitter = SentenceSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            tokenizer=partial(self._encoding.encode, allowed_special="all"),
        )
        split_texts = splitter.split_text(chunk.content)
        split_chunks = [
            TreeChunk(content=split_text.strip(), level=chunk.level, ancestors=chunk.ancestors)
            for split_text in split_texts
        ]
        return split_chunks

    def _combine_chunks(self, chunks: list):
        if len(chunks) == 0:
            return []
        elif len(chunks) == 1:
            if self._count_tokens(chunks[0].content) > self._chunk_size:
                return self._split_text(chunks[0])
            return chunks
        else:
            first_chunks = self._combine_chunks(chunks[:-1])
            current_chunk = first_chunks[-1]
            last_chunk = chunks[-1]
            if self._count_tokens(last_chunk.content) > self._chunk_size:
                first_chunks += self._split_text(last_chunk)
            elif self._count_tokens(current_chunk.content) + self._count_tokens(last_chunk.content) > self._chunk_size:
                first_chunks.append(last_chunk)
            else:
                current_chunk += last_chunk
                first_chunks[-1] = current_chunk
            return first_chunks

    def _fetch_ancestors_to_level(self, ancestors: list[TreeChunk], level: MarkdownLevel) -> list[TreeChunk]:
        if len(ancestors) == 0:
            return ancestors
        if level.value > ancestors[-1].level.value:
            return ancestors
        else:
            return self._fetch_ancestors_to_level(ancestors[:-1], level)

    def chunk_tree(
        self, node: MarkdownNode, ancestors: Optional[list[TreeChunk]] = None
    ) -> list[TreeChunk]:
        """Combines nodes into larger chunks without exceeding max token size."""
        if ancestors is None:
            ancestors = []
        if len(node.children) == 0:
            if node.level.value <= ancestors[-1].level.value:
                new_ancestors = self._fetch_ancestors_to_level(ancestors, node.level)
            else:
                new_ancestors = ancestors.copy()
            return [
                TreeChunk(
                    content=node.formatted_content,
                    ancestors=new_ancestors,
                    level=node.level,
                )
            ]
        else:
            new_ancestors = self._fetch_ancestors_to_level(ancestors, node.level)
            new_ancestors.append(
                TreeChunk(content=node.formatted_content, level=node.level, ancestors=ancestors.copy())
            )
            chunk_sons = []
            for child in node.children:
                chunk_sons += self.chunk_tree(child, ancestors=new_ancestors)
            combined_chunks = self._combine_chunks(chunk_sons)
            return combined_chunks


def add_header_content_to_first_markdown_node(markdown_tree: MarkdownNode) -> MarkdownNode:
    has_children = True
    header_to_add = ""
    current_node = markdown_tree
    counter = 0
    while has_children:
        if counter > 0:  # Avoid putting root node content (= title of document) in the header
            header_to_add += "\n" + current_node.formatted_content
        if len(current_node.children) > 0:
            current_node = current_node.children[0]
            counter += 1
        else:
            has_children = False
            current_node.content = header_to_add
    return markdown_tree


def parse_markdown_to_chunks(
    file_content: str, file_name: str, chunk_size: int = 2048, chunk_overlap: int = 0
) -> list[TreeChunk]:
    markdown_tree = parse_markdown_to_tree(file_content, file_name)
    markdown_tree = add_header_content_to_first_markdown_node(markdown_tree)
    chunker = TreeChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = chunker.chunk_tree(markdown_tree)
    return chunks
