import logging
from typing import Optional, Callable
from functools import partial

from engine.agent.agent import SourceChunk, TermDefinition

LOGGER = logging.getLogger(__name__)

VOCABULARY_TEMPLATE = """\
**Glossary definition of {term}:**
{definition}
"""

SOURCE_TEMPLATE = """\
**Source {source_number}:**
{content}
{metadata}
"""

SourceChunkFormatter = Callable[[SourceChunk], str]


def format_source_chunk_metadata(
    source: SourceChunk,
    llm_metadata_keys: Optional[list[str]] = None,
) -> str:
    """
    Returns a formatted string of metadata from a `SourceChunk` object.
    If `llm_metadata_keys` is provided, only those keys are included.
    If metadata exists, the string is prefixed with "Metadata:".
    If no metadata is available, an empty string is returned.

    Args:
        source (SourceChunk): The `SourceChunk` object containing metadata.
        llm_metadata_keys (list[str]): Metadata keys to include in the output. Defaults to None.

    Returns:
        str: A formatted metadata string or an empty string if no metadata exists.

    Example:
        >>> source = SourceChunk(metadata={"author": "Jane Doe", "year": "2021"})
        >>> format_source_chunk_metadata(source)
        'Metadata:\\nauthor: Jane Doe\\nyear: 2021\\n'
    """
    metadata = source.metadata or {}
    if llm_metadata_keys:
        metadata = {
            key: metadata[key]
            for key in llm_metadata_keys
            if key in metadata and key not in ["reranked_score"]
        }

    if not metadata:
        LOGGER.info("No metadata available for source: %s", source.name)
        return ""

    metadata_str = "Metadata:\n"
    metadata_str += "\n".join(f"{key}: {value}" for key, value in metadata.items())
    return metadata_str


def build_context_from_source_chunks(
    sources: list[SourceChunk],
    source_template: str = SOURCE_TEMPLATE,
    content_formatter: Optional[SourceChunkFormatter] = None,
    metadata_formatter: Optional[SourceChunkFormatter] = None,
    llm_metadata_keys: Optional[list[str]] = None,
    separator: str = "\n\n",
) -> str:
    """
    Builds the full context string from a list of `SourceChunk` objects, applying custom formatters
    to the content and metadata of each source.

    Args:
        sources (list[SourceChunk]): A list of `SourceChunk` objects to format.
        source_template (str): Template string for formatting the source. Defaults to `SOURCE_TEMPLATE`.
        content_formatter (SourceChunkFormatter): A function to format the content
            of the source.
        metadata_formatter (SourceChunkFormatter): A function to format the metadata of the source.
        llm_metadata_keys (list[str]): Metadata keys to include in the output, only relevant
            if the `metadata_formatter` uses this parameter. Defaults to None.
        separator (str): Separator to use between each source. Defaults to "\\n\\n".

    Returns:
        str: The full context string with all sources formatted.

    Example:
        >>> sources = [
                SourceChunk
                    name=1,
                    url="http://example.com",
                    content="Sample content",
                    metadata={"author": "Jane Doe", "year": "2021"},
                )
            ]
        >>> build_context_from_source_chunks(sources)
        **Source 1:**
        Sample content
        Metadata:
        author: Jane Doe
        year: 2021'
    """
    if not sources:
        return ""

    content_formatter = content_formatter or (lambda source: source.content)
    metadata_formatter = metadata_formatter or partial(
        format_source_chunk_metadata, llm_metadata_keys=llm_metadata_keys
    )

    return separator.join(
        source_template.format(
            source_number=index + 1,
            content=content_formatter(source),
            metadata=metadata_formatter(source),
        ).strip()
        for index, source in enumerate(sources)
    )


def build_context_from_vocabulary_chunks(
    vocabulary_chunks: list[TermDefinition],
    vocabulary_template: str = VOCABULARY_TEMPLATE,
    separator: str = "\n\n",
) -> str:
    """
    Builds the full context string from a list of `SourceChunk` objects, applying custom formatters
    to the content and metadata of each source.

    Args:
        vocabulary_chunks (list[TermDefinition]): A list of `VocabularyChunk` objects to format.
        vocabulary_template (str): Template string for formatting the source. Defaults to `VOCABULARY_TEMPLATE`.
        separator (str): Separator to use between each source. Defaults to "\\n\\n".

    Returns:
        str: The full context string with all sources formatted.

    Example:
        >>> vocabulary_chunks = [
                VocabularyChunk
                    term=python,
                    defintion="A programming language",
                )
            ]
        >>> build_context_from_vocabulary_chunks(vocabulary_chunks)
        **Glossary definition of python :**
        A programming language
    """
    if not vocabulary_chunks:
        return ""

    return separator.join(
        vocabulary_template.format(
            term=vocabulary_chunk.term,
            definition=vocabulary_chunk.definition,
        ).strip()
        for index, vocabulary_chunk in enumerate(vocabulary_chunks)
    )
