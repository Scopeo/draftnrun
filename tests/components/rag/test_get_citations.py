from engine.components.rag.formatter import Formatter
from engine.components.types import SourcedResponse


# 1. Test Basic SourceChunk Citations
def test_add_sources_basic(mock_source_chunk_basic):
    formatter = Formatter(add_sources=True)
    response = "This is the response [1]."
    sourced_response = SourcedResponse(response=response, sources=[mock_source_chunk_basic])
    result = formatter.format(sourced_response)
    expected = SourcedResponse(
        response="This is the response [1].\nSources:\n[1] <http://example.com|basic>\n",
        sources=[mock_source_chunk_basic],
    )
    assert result == expected


# 2. Test Multiple SourceChunk Citations
def test_add_sources_multiple(mock_source_chunk_basic, mock_source_chunk_no_metadata):
    formatter = Formatter(add_sources=True)
    response = "This is the response with two sources [1] and [2]."
    sources = [mock_source_chunk_basic, mock_source_chunk_no_metadata]
    sourced_response = SourcedResponse(response=response, sources=sources)
    result = formatter.format(sourced_response)

    expected = SourcedResponse(
        response="This is the response with two sources [1] and [2].\n"
        "Sources:\n"
        "[1] <http://example.com|basic>\n"
        "[2] <http://example2.com|no_metadata>\n",
        sources=sources,
    )
    assert result == expected


# 3. Test No SourceChunks Referenced
def test_add_sources_no_citations(mock_source_chunk_basic):
    response = "This is the response with no sources."
    formatter = Formatter()
    sourced_response = SourcedResponse(response=response, sources=[mock_source_chunk_basic])
    result = formatter.format(sourced_response)

    # Since there are no sources cited, it should return the original response.
    expected = SourcedResponse(response="This is the response with no sources.", sources=[])
    assert result == expected


# 4. Test SourceChunk Not in Response
def test_add_sources_missing_source_number(mock_source_chunk_basic, mock_source_chunk_no_metadata):
    response = "This is the response with an out-of-range source [3]."
    sources = [mock_source_chunk_basic, mock_source_chunk_no_metadata]
    formatter = Formatter()
    sourced_response = SourcedResponse(response=response, sources=sources)

    result = formatter.format(sourced_response)

    # Since source [3] is out-of-range, it should not add any citations.
    expected = SourcedResponse(response="This is the response with an out-of-range source [].", sources=[])
    assert result == expected


# 5. Test Citations with Page Number
def test_add_sources_with_page_number(mock_source_chunk_with_page_number):
    response = "This is the response [1]."
    formatter = Formatter(add_sources=True)
    sourced_response = SourcedResponse(response=response, sources=[mock_source_chunk_with_page_number])
    result = formatter.format(sourced_response)

    expected = SourcedResponse(
        response="This is the response [1].\nSources:\n[1] <http://example5.com|with_page_number page 300>\n",
        sources=[mock_source_chunk_with_page_number],
    )
    assert result == expected


# 6. Test Citations with Special Characters in Metadata
def test_add_sources_special_characters(mock_source_chunk_special_characters):
    response = "Here is the response [1]."
    formatter = Formatter(add_sources=True)
    sourced_response = SourcedResponse(response=response, sources=[mock_source_chunk_special_characters])
    result = formatter.format(sourced_response)

    expected = SourcedResponse(
        response="Here is the response [1].\nSources:\n[1] <http://example4.com|special_characters>\n",
        sources=[mock_source_chunk_special_characters],
    )
    assert result == expected


# 7. Test No Source Nodes Provided
def test_add_sources_no_source_nodes():
    response = "This is the response [1]."
    formatter = Formatter()
    sourced_response = SourcedResponse(response=response, sources=[])
    result = formatter.format(sourced_response)

    # Since no source nodes are provided, the response should remain the same.
    expected = SourcedResponse(response="This is the response [1].", sources=[])
    assert result == expected


# 8. Test with sources starting from 2 to 3
def test_add_sources_numeration_starting_above_1(
    mock_source_chunk_basic, mock_source_chunk_no_metadata, mock_source_chunk_special_characters
):
    response = "This is the response [3][2]."
    formatter = Formatter(add_sources=True)
    sourced_response = SourcedResponse(
        response=response,
        sources=[
            mock_source_chunk_basic,
            mock_source_chunk_no_metadata,
            mock_source_chunk_special_characters,
        ],
    )
    result = formatter.format(sourced_response)
    expected = SourcedResponse(
        response="This is the response [1][2].\n"
        "Sources:\n"
        "[1] <http://example4.com|special_characters>\n"
        "[2] <http://example2.com|no_metadata>\n",
        sources=[mock_source_chunk_special_characters, mock_source_chunk_no_metadata],
    )
    assert result == expected


# 9. Test with multiple encapsulated citations
def test_add_multiple_encapsulated_sources(
    mock_source_chunk_basic, mock_source_chunk_no_metadata, mock_source_chunk_special_characters
):
    response = "This is the response [1,99,2]."
    formatter = Formatter(add_sources=True)
    sourced_response = SourcedResponse(
        response=response,
        sources=[
            mock_source_chunk_special_characters,
            mock_source_chunk_no_metadata,
            mock_source_chunk_basic,
        ],
    )

    result = formatter.format(sourced_response)
    expected = SourcedResponse(
        response="This is the response [1,,2].\n"
        "Sources:\n"
        "[1] <http://example4.com|special_characters>\n"
        "[2] <http://example2.com|no_metadata>\n",
        sources=[mock_source_chunk_special_characters, mock_source_chunk_no_metadata],
    )
    assert result == expected


# 10. Test with the same sources mention multiple time
def test_sources_mention_multiple_time(
    mock_source_chunk_basic, mock_source_chunk_no_metadata, mock_source_chunk_special_characters
):
    response = "This is the response [3][2]. Here is another text [3]. Here is the last part [2]."
    formatter = Formatter(add_sources=True)
    sourced_response = SourcedResponse(
        response=response,
        sources=[mock_source_chunk_basic, mock_source_chunk_no_metadata, mock_source_chunk_special_characters],
    )
    result = formatter.format(sourced_response)
    expected = SourcedResponse(
        response="This is the response [1][2]. Here is another text [1]. Here is the last part [2].\n"
        "Sources:\n"
        "[1] <http://example4.com|special_characters>\n"
        "[2] <http://example2.com|no_metadata>\n",
        sources=[mock_source_chunk_special_characters, mock_source_chunk_no_metadata],
    )
    assert result == expected
