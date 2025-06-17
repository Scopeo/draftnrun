from engine.agent.build_context import build_context_from_source_chunks


# 1. Test Basic SourceChunk Formatting
def test_basic_source_chunk_formatting(mock_source_chunk_basic):
    result = build_context_from_source_chunks([mock_source_chunk_basic])
    expected = "**Source 1:**\n" "Sample content\n" "Metadata:\nauthor: Jane Doe\nyear: 2021"
    assert result == expected


# 2. Test SourceChunk Without Metadata
def test_source_chunk_no_metadata(mock_source_chunk_no_metadata):
    result = build_context_from_source_chunks([mock_source_chunk_no_metadata])
    expected = "**Source 1:**\n" "Another sample content"
    assert result == expected  # No metadata is expected in the output


# 3. Test SourceChunk With Empty Content
def test_source_chunk_empty_content(mock_source_chunk_empty_content):
    result = build_context_from_source_chunks([mock_source_chunk_empty_content])
    expected = "**Source 1:**\n" "\n" "Metadata:\nauthor: John Smith"  # Empty content
    assert result == expected


# 4. Test SourceChunk Without URL
def test_source_chunk_no_url(mock_source_chunk_no_url):
    result = build_context_from_source_chunks([mock_source_chunk_no_url])
    expected = "**Source 1:**\n" "Content without URL\n" "Metadata:\nauthor: Unknown"  # No URL
    assert result == expected


# 5. Test Special Characters Handling
def test_source_chunk_special_characters(mock_source_chunk_special_characters):
    result = build_context_from_source_chunks([mock_source_chunk_special_characters])
    expected = (
        "**Source 1:**\n"
        "Content with special characters! @#$%^&*()\n"
        "Metadata:\nauthor: Alice\ndescription: Contains !@#$%^&*() symbols"
    )
    assert result == expected


# 6. Test With Many Metadata Fields
def test_source_chunk_filter_metadata(mock_source_chunk_many_metadata):
    result = build_context_from_source_chunks(
        [mock_source_chunk_many_metadata], llm_metadata_keys=["author", "year", "keywords"]
    )
    expected = (
        "**Source 1:**\n"
        "Content with a lot of metadata\n"
        "Metadata:\n"
        "author: Jane Doe\n"
        "year: 2021\n"
        "keywords: AI, Python, Programming"
    )
    assert result == expected


# 7. Test Custom Template and Content Formatting
def test_custom_template_and_content_formatter(mock_source_chunk_basic):
    custom_template = "Source #{source_number}:\nData:\n{content}\n\n{metadata}"

    def custom_content_formatter(source):
        return f"Custom formatted content: {source.content}"

    result = build_context_from_source_chunks(
        [mock_source_chunk_basic],
        source_template=custom_template,
        content_formatter=custom_content_formatter,
    )

    expected = (
        "Source #1:\n" "Data:\nCustom formatted content: Sample content\n\n" "Metadata:\nauthor: Jane Doe\nyear: 2021"
    )

    assert result == expected


# 8. Test Custom Metadata Formatting
def test_custom_metadata_formatter(mock_source_chunk_basic):
    def custom_metadata_formatter(source):
        return f"Author is {source.metadata.get('author', 'Unknown')}"

    result = build_context_from_source_chunks(
        [mock_source_chunk_basic],
        metadata_formatter=custom_metadata_formatter,
    )

    expected = "**Source 1:**\n" "Sample content\n" "Author is Jane Doe"
    assert result == expected


# 9. Test Advanced Content Formatting
def test_advanced_content_formatting(mock_source_chunk_many_metadata):
    def custom_content_formatter(source):
        truncated_content = source.content[:12] + "..." if len(source.content) > 5 else source.content
        return f"{source.metadata.get('author', 'Unknown')} wrote: {truncated_content}"

    result = build_context_from_source_chunks(
        [mock_source_chunk_many_metadata],
        content_formatter=custom_content_formatter,
        metadata_formatter=lambda source: "",
    )

    expected = "**Source 1:**\n" "Jane Doe wrote: Content with..."

    assert result == expected
