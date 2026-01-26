from ada_backend.schemas.pipeline.graph_schema import PlaygroundFieldType
from ada_backend.services.graph.playground_utils import classify_playground_field, classify_schema_fields


def test_classify_messages_field():
    """Test that 'messages' field is classified as MESSAGES."""
    result = classify_playground_field("messages", [{"role": "user", "content": "Hello"}])
    assert result == PlaygroundFieldType.MESSAGES


def test_classify_file_field_openai_format():
    """Test that file field in OpenAI format is classified as FILE."""
    file_value = {"type": "file", "file": {"filename": "", "file_data": ""}}
    result = classify_playground_field("document", file_value)
    assert result == PlaygroundFieldType.FILE


def test_classify_simple_field():
    """Test that simple fields are classified as SIMPLE."""
    result = classify_playground_field("user_name", "John Doe")
    assert result == PlaygroundFieldType.SIMPLE


def test_classify_json_field():
    """Test that deeply nested fields are classified as JSON."""
    nested_value = {"level1": {"level2": {"level3": {"level4": "deep"}}}}
    result = classify_playground_field("config", nested_value)
    assert result == PlaygroundFieldType.JSON


def test_classify_schema_fields_mixed():
    """Test classifying a schema with multiple field types."""
    schema = {
        "messages": [{"role": "user", "content": "Hello"}],
        "document_upload": {"type": "file", "file": {"filename": "", "file_data": ""}},
        "user_name": "John",
        "settings": {"theme": {"colors": {"primary": {"dark": "#000"}}}},
    }

    result = classify_schema_fields(schema)

    assert result["messages"] == PlaygroundFieldType.MESSAGES
    assert result["document_upload"] == PlaygroundFieldType.FILE
    assert result["user_name"] == PlaygroundFieldType.SIMPLE
    assert result["settings"] == PlaygroundFieldType.JSON


def test_file_field_without_file_key():
    """Test that file type without 'file' key is not classified as FILE."""
    incomplete_file = {"type": "file"}  # Missing "file" key
    result = classify_playground_field("document", incomplete_file)
    assert result == PlaygroundFieldType.SIMPLE


def test_multiple_file_fields():
    """Test schema with multiple file fields."""
    schema = {
        "resume": {"type": "file", "file": {"filename": "", "file_data": ""}},
        "cover_letter": {"type": "file", "file": {"filename": "", "file_data": ""}},
        "portfolio": {"type": "file", "file": {"filename": "", "file_data": ""}},
    }

    result = classify_schema_fields(schema)

    assert result["resume"] == PlaygroundFieldType.FILE
    assert result["cover_letter"] == PlaygroundFieldType.FILE
    assert result["portfolio"] == PlaygroundFieldType.FILE
    assert len(result) == 3


def test_empty_schema():
    """Test handling of empty schema."""
    result = classify_schema_fields({})
    assert result == {}


def test_file_field_priority_over_depth():
    """Test that FILE type takes priority over depth-based classification."""
    # This has depth > 2 but should be FILE because of type marker
    file_value = {"type": "file", "file": {"nested": {"deep": "value"}}}
    result = classify_playground_field("document", file_value)
    assert result == PlaygroundFieldType.FILE
